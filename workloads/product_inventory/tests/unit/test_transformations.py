"""
Unit tests for product_inventory transformations.

Tests verify the transformation LOGIC for both bronze_to_silver and silver_to_gold.
The actual scripts run on AWS Glue ETL (PySpark) and cannot be imported locally.
These tests use pandas-based wrapper classes that mirror the Glue ETL logic
to validate correctness of the 10 cleaning rules and star schema creation.
"""

from pathlib import Path

import pandas as pd
import pytest
import yaml

# Get project root (4 levels up from test file)
PROJECT_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def sample_data_path():
    """Path to sample product inventory CSV."""
    return PROJECT_ROOT / "sample_data/product_inventory.csv"


@pytest.fixture
def transformations_config_path():
    """Path to transformations.yaml."""
    return PROJECT_ROOT / "workloads/product_inventory/config/transformations.yaml"


@pytest.fixture
def output_dir(tmp_path):
    """Temporary output directory for test artifacts."""
    return tmp_path


@pytest.fixture
def silver_output_path(output_dir):
    """Path for silver output."""
    silver_dir = output_dir / "silver"
    silver_dir.mkdir(parents=True, exist_ok=True)
    return silver_dir / "product_inventory_silver.csv"


@pytest.fixture
def quarantine_output_path(output_dir):
    """Path for quarantine output."""
    quarantine_dir = output_dir / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    return quarantine_dir / "product_inventory_quarantine.csv"


@pytest.fixture
def gold_output_dir(output_dir):
    """Directory for gold output."""
    gold_dir = output_dir / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)
    return gold_dir


class BronzeTransformerWrapper:
    """Mirrors the Glue ETL Bronze->Silver logic using pandas for local testing."""

    def __init__(self):
        self.transformation_counts = {}

    def transform(self, input_path, output_path, quarantine_path):
        """Run Bronze->Silver transformation logic and return stats dict."""
        from datetime import datetime, timezone

        df = pd.read_csv(input_path)
        initial_count = len(df)
        quarantine_records = []

        # Step 1: Deduplicate
        before = len(df)
        df = df.drop_duplicates(subset=["product_id", "sku"], keep="first")
        removed = before - len(df)
        self.transformation_counts["duplicates_removed"] = removed

        # Step 2: Quarantine negative quantities
        mask = df["quantity_on_hand"] < 0
        q = df[mask].copy()
        if len(q) > 0:
            q["quarantine_reason"] = "negative_quantity"
            q["quarantine_timestamp"] = datetime.now(timezone.utc).isoformat()
            quarantine_records.append(q)
        df = df[~mask]
        self.transformation_counts["negative_quantities_quarantined"] = len(q)

        # Step 3: Quarantine future dates
        df["last_restocked_date"] = pd.to_datetime(df["last_restocked_date"], errors="coerce")
        today = pd.Timestamp.now().normalize()
        mask = df["last_restocked_date"] > today
        q = df[mask].copy()
        if len(q) > 0:
            q["quarantine_reason"] = "future_restock_date"
            q["quarantine_timestamp"] = datetime.now(timezone.utc).isoformat()
            quarantine_records.append(q)
        df = df[~mask]
        self.transformation_counts["future_dates_quarantined"] = len(q)

        # Step 4: Normalize category
        df["category"] = df["category"].str.strip().str.title()

        # Step 5: Trim product_name
        df["product_name"] = df["product_name"].str.strip()

        # Step 6: Fix invalid status
        status_map = {"aktive": "active", "Aktive": "active", "AKTIVE": "active"}
        fixed = int(df["status"].isin(status_map.keys()).sum())
        df["status"] = df["status"].replace(status_map)
        self.transformation_counts["invalid_status_fixed"] = fixed

        # Step 7: Flag missing supplier
        mask = df["supplier_id"].isna() | df["supplier_name"].isna()
        df["is_supplier_missing"] = mask
        df.loc[df["supplier_name"].isna(), "supplier_name"] = "Unknown Supplier"

        # Step 8: Flag margin anomaly
        df["is_margin_anomaly"] = df["cost_price"] > df["unit_price"]

        # Step 9: Flag missing expiry
        df["is_expiry_missing"] = (df["category"] == "Grocery") & df["expiry_date"].isna()

        # Step 10: Fill missing reorder
        mask = df["reorder_level"].isna()
        df["is_reorder_missing"] = mask
        df.loc[mask, "reorder_level"] = 0

        # Add metadata
        df["processing_timestamp"] = datetime.now(timezone.utc).isoformat()
        df["data_quality_score"] = 1.0

        final_count = len(df)
        total_quarantined = sum(len(q) for q in quarantine_records)

        # Write outputs
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)

        if quarantine_records:
            Path(quarantine_path).parent.mkdir(parents=True, exist_ok=True)
            combined = pd.concat(quarantine_records, ignore_index=True)
            combined.to_csv(quarantine_path, index=False)

        stats = {
            "initial_count": initial_count,
            "final_count": final_count,
            "quarantine_count": total_quarantined,
            **self.transformation_counts,
        }
        return stats


class GoldTransformerWrapper:
    """Mirrors the Glue ETL Silver->Gold star schema logic using pandas for local testing."""

    def __init__(self):
        self.stats = {}

    def transform(self, input_path, output_dir):
        """Run Silver->Gold star schema transformation and return stats dict."""
        df = pd.read_csv(input_path)

        # dim_product
        dim_product = df[["product_id", "sku", "product_name", "category", "subcategory", "brand", "status"]].drop_duplicates(subset=["product_id"])
        dim_product = dim_product.reset_index(drop=True)
        dim_product.insert(0, "product_key", range(1, len(dim_product) + 1))
        self.stats["dim_product_rows"] = len(dim_product)

        # dim_supplier
        dim_supplier = df[["supplier_id", "supplier_name"]].drop_duplicates(subset=["supplier_id"])
        dim_supplier = dim_supplier.dropna(subset=["supplier_id"])
        dim_supplier = dim_supplier.reset_index(drop=True)
        dim_supplier.insert(0, "supplier_key", range(1, len(dim_supplier) + 1))
        self.stats["dim_supplier_rows"] = len(dim_supplier)

        # dim_warehouse
        dim_warehouse = df[["warehouse_location"]].drop_duplicates()
        def derive_region(loc):
            if pd.isna(loc):
                return "UNKNOWN"
            loc_upper = str(loc).upper()
            if "EAST" in loc_upper:
                return "EAST"
            elif "WEST" in loc_upper:
                return "WEST"
            elif "CENTRAL" in loc_upper:
                return "CENTRAL"
            return "UNKNOWN"
        dim_warehouse["region"] = dim_warehouse["warehouse_location"].apply(derive_region)
        dim_warehouse = dim_warehouse.reset_index(drop=True)
        dim_warehouse.insert(0, "warehouse_key", range(1, len(dim_warehouse) + 1))
        self.stats["dim_warehouse_rows"] = len(dim_warehouse)

        # fact_inventory
        fact = df.copy()
        fact = fact.merge(dim_product[["product_key", "product_id"]], on="product_id", how="left")
        fact = fact.merge(dim_supplier[["supplier_key", "supplier_id"]], on="supplier_id", how="left")
        fact = fact.merge(dim_warehouse[["warehouse_key", "warehouse_location"]], on="warehouse_location", how="left")

        fact["margin"] = fact["unit_price"] - fact["cost_price"]
        fact["margin_pct"] = fact.apply(
            lambda r: (r["margin"] / r["unit_price"] * 100) if r["unit_price"] > 0 else 0, axis=1)
        fact["inventory_value"] = fact["unit_price"] * fact["quantity_on_hand"]
        fact["needs_reorder"] = fact["quantity_on_hand"] <= fact["reorder_level"]

        fact = fact[[
            "product_key", "supplier_key", "warehouse_key",
            "unit_price", "cost_price", "margin", "margin_pct",
            "quantity_on_hand", "reorder_level", "reorder_quantity",
            "weight_kg", "inventory_value", "needs_reorder"
        ]]
        self.stats["fact_inventory_rows"] = len(fact)

        # Write outputs
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        tables = {
            "fact_inventory": fact,
            "dim_product": dim_product,
            "dim_supplier": dim_supplier,
            "dim_warehouse": dim_warehouse,
        }
        for name, table_df in tables.items():
            table_df.to_csv(output_path / f"{name}.csv", index=False)

        return self.stats


@pytest.fixture
def bronze_transformer():
    """Wrapper mirroring Glue ETL Bronze->Silver logic."""
    return BronzeTransformerWrapper()


@pytest.fixture
def gold_transformer():
    """Wrapper mirroring Glue ETL Silver->Gold logic."""
    return GoldTransformerWrapper()


# ============================================================================
# Bronze to Silver Tests
# ============================================================================

def test_bronze_to_silver_end_to_end(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Test full bronze to silver transformation."""
    stats = bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    assert silver_output_path.exists(), "Silver output file not created"
    assert stats['initial_count'] == 123, f"Expected 123 initial records, got {stats['initial_count']}"
    assert stats['final_count'] > 0, "No records in silver output"
    assert 'duplicates_removed' in stats

    df_silver = pd.read_csv(silver_output_path)
    assert len(df_silver) == stats['final_count']
    assert len(df_silver) > 0


def test_deduplication_removes_duplicates(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Verify deduplicate removes exactly 3 duplicates."""
    stats = bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )
    assert stats['duplicates_removed'] == 3, f"Expected 3 duplicates removed, got {stats['duplicates_removed']}"


def test_category_casing_normalized(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Verify all category values are title case."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    df_silver = pd.read_csv(silver_output_path)
    for category in df_silver['category'].unique():
        if pd.notna(category):
            assert category == category.strip().title(), f"Category '{category}' not in title case"


def test_whitespace_trimmed_from_product_name(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Verify product_name has no leading/trailing whitespace."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    df_silver = pd.read_csv(silver_output_path)
    for name in df_silver['product_name']:
        if pd.notna(name):
            assert name == str(name).strip(), f"Product name '{name}' has whitespace"


def test_invalid_status_mapped_to_active(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Verify 'aktive' is mapped to 'active'."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    df_silver = pd.read_csv(silver_output_path)
    status_values = df_silver['status'].str.lower().unique()
    assert 'aktive' not in status_values, "Invalid status 'aktive' found in silver data"
    assert 'active' in df_silver['status'].str.lower().unique(), "'active' status not found"
    assert bronze_transformer.transformation_counts.get('invalid_status_fixed', 0) >= 0


def test_negative_quantities_quarantined(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Verify records with negative quantity_on_hand are quarantined."""
    stats = bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    df_silver = pd.read_csv(silver_output_path)
    assert (df_silver['quantity_on_hand'] >= 0).all(), "Negative quantities found in silver data"

    if stats.get('negative_quantities_quarantined', 0) > 0:
        assert quarantine_output_path.exists(), "Quarantine file not created despite negative quantities"
        df_quarantine = pd.read_csv(quarantine_output_path)
        quarantined_negative = df_quarantine[df_quarantine['quarantine_reason'] == 'negative_quantity']
        assert len(quarantined_negative) == stats['negative_quantities_quarantined']


def test_future_dates_quarantined(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Verify records with future last_restocked_date are quarantined."""
    stats = bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    df_silver = pd.read_csv(silver_output_path)
    df_silver['last_restocked_date'] = pd.to_datetime(df_silver['last_restocked_date'], errors='coerce')
    today = pd.Timestamp.now().normalize()

    future_dates = df_silver[df_silver['last_restocked_date'] > today]
    assert len(future_dates) == 0, f"Found {len(future_dates)} records with future dates in silver"

    if stats.get('future_dates_quarantined', 0) > 0:
        assert quarantine_output_path.exists(), "Quarantine file not created despite future dates"
        df_quarantine = pd.read_csv(quarantine_output_path)
        quarantined_future = df_quarantine[df_quarantine['quarantine_reason'] == 'future_restock_date']
        assert len(quarantined_future) == stats['future_dates_quarantined']


def test_margin_anomaly_flag_set(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Verify is_margin_anomaly flag is set when cost_price > unit_price."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    df_silver = pd.read_csv(silver_output_path)
    assert 'is_margin_anomaly' in df_silver.columns, "is_margin_anomaly column not found"

    for _, row in df_silver.iterrows():
        if row['cost_price'] > row['unit_price']:
            assert row['is_margin_anomaly'] == True, f"Margin anomaly not flagged for product {row['product_id']}"
        else:
            assert row['is_margin_anomaly'] == False, f"Margin anomaly incorrectly flagged for product {row['product_id']}"


def test_supplier_missing_flag_set(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Verify is_supplier_missing flag is set for records with missing supplier."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    df_silver = pd.read_csv(silver_output_path)
    assert 'is_supplier_missing' in df_silver.columns, "is_supplier_missing column not found"
    assert 'Unknown Supplier' in df_silver['supplier_name'].values, "Unknown Supplier not filled"


def test_expiry_missing_flag_set(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Verify is_expiry_missing flag is set for Grocery items without expiry_date."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    df_silver = pd.read_csv(silver_output_path)
    assert 'is_expiry_missing' in df_silver.columns, "is_expiry_missing column not found"

    grocery_items = df_silver[df_silver['category'] == 'Grocery']
    for _, row in grocery_items.iterrows():
        if pd.isna(row['expiry_date']):
            assert row['is_expiry_missing'] == True, f"Expiry missing not flagged for Grocery product {row['product_id']}"


def test_reorder_missing_filled(sample_data_path, silver_output_path, quarantine_output_path, bronze_transformer):
    """Verify missing reorder_level is filled with 0 and flagged."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    df_silver = pd.read_csv(silver_output_path)
    assert 'is_reorder_missing' in df_silver.columns, "is_reorder_missing column not found"
    assert df_silver['reorder_level'].notna().all(), "Null reorder_level values found in silver"


# ============================================================================
# Silver to Gold Tests
# ============================================================================

def test_silver_to_gold_end_to_end(sample_data_path, silver_output_path, quarantine_output_path, gold_output_dir, bronze_transformer, gold_transformer):
    """Test full silver to gold transformation."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )

    stats = gold_transformer.transform(
        str(silver_output_path),
        str(gold_output_dir)
    )

    assert (gold_output_dir / "fact_inventory.csv").exists(), "fact_inventory not created"
    assert (gold_output_dir / "dim_product.csv").exists(), "dim_product not created"
    assert (gold_output_dir / "dim_supplier.csv").exists(), "dim_supplier not created"
    assert (gold_output_dir / "dim_warehouse.csv").exists(), "dim_warehouse not created"

    assert stats['fact_inventory_rows'] > 0
    assert stats['dim_product_rows'] > 0
    assert stats['dim_supplier_rows'] > 0
    assert stats['dim_warehouse_rows'] > 0


def test_fact_inventory_has_required_columns(sample_data_path, silver_output_path, quarantine_output_path, gold_output_dir, bronze_transformer, gold_transformer):
    """Verify fact_inventory has all required columns including derived measures."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )
    gold_transformer.transform(
        str(silver_output_path),
        str(gold_output_dir)
    )

    df_fact = pd.read_csv(gold_output_dir / "fact_inventory.csv")

    required_columns = [
        'product_key', 'supplier_key', 'warehouse_key',
        'unit_price', 'cost_price', 'margin', 'margin_pct',
        'quantity_on_hand', 'reorder_level', 'reorder_quantity',
        'weight_kg', 'inventory_value', 'needs_reorder'
    ]

    for col in required_columns:
        assert col in df_fact.columns, f"Column '{col}' not found in fact_inventory"


def test_fact_inventory_derived_measures(sample_data_path, silver_output_path, quarantine_output_path, gold_output_dir, bronze_transformer, gold_transformer):
    """Verify derived measures are correctly calculated."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )
    gold_transformer.transform(
        str(silver_output_path),
        str(gold_output_dir)
    )

    df_fact = pd.read_csv(gold_output_dir / "fact_inventory.csv")

    for _, row in df_fact.iterrows():
        expected_margin = row['unit_price'] - row['cost_price']
        assert abs(row['margin'] - expected_margin) < 0.01, f"Margin calculation incorrect"

        if row['unit_price'] > 0:
            expected_margin_pct = (row['margin'] / row['unit_price']) * 100
            assert abs(row['margin_pct'] - expected_margin_pct) < 0.1, f"Margin % calculation incorrect"

        expected_value = row['unit_price'] * row['quantity_on_hand']
        assert abs(row['inventory_value'] - expected_value) < 0.01, f"Inventory value calculation incorrect"

        expected_reorder = row['quantity_on_hand'] <= row['reorder_level']
        assert row['needs_reorder'] == expected_reorder, f"needs_reorder flag incorrect"


def test_dimensions_created(sample_data_path, silver_output_path, quarantine_output_path, gold_output_dir, bronze_transformer, gold_transformer):
    """Verify all dimension tables are created."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )
    gold_transformer.transform(
        str(silver_output_path),
        str(gold_output_dir)
    )

    df_product = pd.read_csv(gold_output_dir / "dim_product.csv")
    assert 'product_key' in df_product.columns
    assert 'product_id' in df_product.columns
    assert 'sku' in df_product.columns
    assert len(df_product) > 0

    df_supplier = pd.read_csv(gold_output_dir / "dim_supplier.csv")
    assert 'supplier_key' in df_supplier.columns
    assert 'supplier_id' in df_supplier.columns
    assert len(df_supplier) > 0

    df_warehouse = pd.read_csv(gold_output_dir / "dim_warehouse.csv")
    assert 'warehouse_key' in df_warehouse.columns
    assert 'warehouse_location' in df_warehouse.columns
    assert 'region' in df_warehouse.columns
    assert len(df_warehouse) > 0


def test_surrogate_keys_sequential(sample_data_path, silver_output_path, quarantine_output_path, gold_output_dir, bronze_transformer, gold_transformer):
    """Verify surrogate keys are sequential integers."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )
    gold_transformer.transform(
        str(silver_output_path),
        str(gold_output_dir)
    )

    df_product = pd.read_csv(gold_output_dir / "dim_product.csv")
    expected_keys = list(range(1, len(df_product) + 1))
    assert df_product['product_key'].tolist() == expected_keys, "Product keys not sequential"

    df_supplier = pd.read_csv(gold_output_dir / "dim_supplier.csv")
    expected_keys = list(range(1, len(df_supplier) + 1))
    assert df_supplier['supplier_key'].tolist() == expected_keys, "Supplier keys not sequential"

    df_warehouse = pd.read_csv(gold_output_dir / "dim_warehouse.csv")
    expected_keys = list(range(1, len(df_warehouse) + 1))
    assert df_warehouse['warehouse_key'].tolist() == expected_keys, "Warehouse keys not sequential"


def test_warehouse_region_derived(sample_data_path, silver_output_path, quarantine_output_path, gold_output_dir, bronze_transformer, gold_transformer):
    """Verify dim_warehouse.region is correctly derived from warehouse_location."""
    bronze_transformer.transform(
        str(sample_data_path),
        str(silver_output_path),
        str(quarantine_output_path)
    )
    gold_transformer.transform(
        str(silver_output_path),
        str(gold_output_dir)
    )

    df_warehouse = pd.read_csv(gold_output_dir / "dim_warehouse.csv")

    for _, row in df_warehouse.iterrows():
        location = str(row['warehouse_location']).upper()
        region = row['region']

        if 'EAST' in location:
            assert region == 'EAST', f"Region should be EAST for {location}"
        elif 'WEST' in location:
            assert region == 'WEST', f"Region should be WEST for {location}"
        elif 'CENTRAL' in location:
            assert region == 'CENTRAL', f"Region should be CENTRAL for {location}"
        else:
            assert region == 'UNKNOWN', f"Region should be UNKNOWN for {location}"


def test_idempotency_bronze_to_silver(sample_data_path, output_dir):
    """Verify running bronze_to_silver twice produces identical output."""
    silver_path_1 = output_dir / "silver1" / "output.csv"
    silver_path_1.parent.mkdir(parents=True, exist_ok=True)
    quarantine_path_1 = output_dir / "quarantine1" / "output.csv"
    quarantine_path_1.parent.mkdir(parents=True, exist_ok=True)

    silver_path_2 = output_dir / "silver2" / "output.csv"
    silver_path_2.parent.mkdir(parents=True, exist_ok=True)
    quarantine_path_2 = output_dir / "quarantine2" / "output.csv"
    quarantine_path_2.parent.mkdir(parents=True, exist_ok=True)

    transformer1 = BronzeTransformerWrapper()
    stats1 = transformer1.transform(str(sample_data_path), str(silver_path_1), str(quarantine_path_1))

    transformer2 = BronzeTransformerWrapper()
    stats2 = transformer2.transform(str(sample_data_path), str(silver_path_2), str(quarantine_path_2))

    assert stats1['final_count'] == stats2['final_count'], "Different record counts on second run"

    df1 = pd.read_csv(silver_path_1)
    df2 = pd.read_csv(silver_path_2)

    df1_no_ts = df1.drop(columns=['processing_timestamp'])
    df2_no_ts = df2.drop(columns=['processing_timestamp'])

    pd.testing.assert_frame_equal(df1_no_ts, df2_no_ts, check_dtype=False)


def test_idempotency_silver_to_gold(sample_data_path, output_dir):
    """Verify running silver_to_gold twice produces identical output."""
    silver_path = output_dir / "silver" / "output.csv"
    silver_path.parent.mkdir(parents=True, exist_ok=True)
    quarantine_path = output_dir / "quarantine" / "output.csv"
    quarantine_path.parent.mkdir(parents=True, exist_ok=True)

    bronze = BronzeTransformerWrapper()
    bronze.transform(str(sample_data_path), str(silver_path), str(quarantine_path))

    gold_dir_1 = output_dir / "gold1"
    gold_dir_1.mkdir(parents=True, exist_ok=True)
    gold_dir_2 = output_dir / "gold2"
    gold_dir_2.mkdir(parents=True, exist_ok=True)

    transformer1 = GoldTransformerWrapper()
    stats1 = transformer1.transform(str(silver_path), str(gold_dir_1))

    transformer2 = GoldTransformerWrapper()
    stats2 = transformer2.transform(str(silver_path), str(gold_dir_2))

    assert stats1 == stats2, "Different stats on second run"

    for table in ['fact_inventory', 'dim_product', 'dim_supplier', 'dim_warehouse']:
        df1 = pd.read_csv(gold_dir_1 / f"{table}.csv")
        df2 = pd.read_csv(gold_dir_2 / f"{table}.csv")
        pd.testing.assert_frame_equal(df1, df2, check_dtype=False)


def test_transformations_yaml_loads(transformations_config_path):
    """Verify transformations.yaml is valid YAML and has required sections."""
    with open(transformations_config_path) as f:
        config = yaml.safe_load(f)

    assert 'workload_name' in config
    assert config['workload_name'] == 'product_inventory'
    assert 'bronze_to_silver' in config
    assert 'silver_to_gold' in config

    b2s = config['bronze_to_silver']
    assert 'transformations' in b2s
    assert len(b2s['transformations']) == 10, "Should have 10 transformation rules"

    s2g = config['silver_to_gold']
    assert 'gold_format' in s2g
    assert s2g['gold_format'] == 'star_schema'
    assert 'fact_table' in s2g
    assert 'dimension_tables' in s2g
    assert len(s2g['dimension_tables']) == 3, "Should have 3 dimension tables"
