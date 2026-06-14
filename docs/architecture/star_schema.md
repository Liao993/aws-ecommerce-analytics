# Olist OLAP Star Schema — Data Model Design


## Design Decisions Summary

| Decision | Choice | Rationale |
|---|---|---|
| **Schema type** | Star (not snowflake) | Dimensions are small; join simplicity outweighs normalization savings. |
| **Primary fact grain** | One row per order item | Enables item-level and order-level analysis from a single table. |
| **Fact tables** | 3: `fact_order_items`, `fact_orders`, `fact_payments` | Different grains cannot share a fact table. |
| **Surrogate keys** | `dbt_utils.generate_surrogate_key()` | Consistent, testable, resilient to upstream key changes. |
| **SCD strategy** | Type 2 for customers and sellers; Type 1 for products | Customers/sellers change location; product attributes don't need history. |
| **dim_date** | Generated in dbt via date-spine macro | No date dimension in Olist source; industry-standard pattern. |

---

## Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    fact_order_items {
        VARCHAR order_id FK
        INTEGER order_item_id
        VARCHAR order_key FK
        VARCHAR customer_key FK
        VARCHAR seller_key FK
        VARCHAR product_key FK
        VARCHAR date_key FK
        DECIMAL price
        DECIMAL freight_value
        TIMESTAMP shipping_limit_date
    }
    fact_orders {
        VARCHAR order_id PK
        VARCHAR order_key
        VARCHAR customer_key FK
        VARCHAR date_key FK
        VARCHAR order_status
        INTEGER delivery_days
        INTEGER estimated_delivery_days
        BOOLEAN is_delivered_on_time
        TIMESTAMP order_purchase_timestamp
        TIMESTAMP order_delivered_customer_date
        TIMESTAMP order_estimated_delivery_date
    }
    fact_payments {
        VARCHAR order_id FK
        INTEGER payment_sequential
        VARCHAR order_key FK
        VARCHAR payment_type
        INTEGER payment_installments
        DECIMAL payment_value
    }
    dim_customers {
        VARCHAR customer_key PK
        VARCHAR customer_id
        VARCHAR customer_unique_id
        VARCHAR customer_city
        VARCHAR customer_state
        VARCHAR customer_zip_code_prefix
        TIMESTAMP dbt_valid_from
        TIMESTAMP dbt_valid_to
        BOOLEAN is_current
    }
    dim_sellers {
        VARCHAR seller_key PK
        VARCHAR seller_id
        VARCHAR seller_city
        VARCHAR seller_state
        VARCHAR seller_zip_code_prefix
        TIMESTAMP dbt_valid_from
        TIMESTAMP dbt_valid_to
        BOOLEAN is_current
    }
    dim_products {
        VARCHAR product_key PK
        VARCHAR product_id
        VARCHAR product_category_name
        VARCHAR product_category_name_english
        INTEGER product_weight_g
        INTEGER product_photos_qty
        DECIMAL product_length_cm
        DECIMAL product_height_cm
        DECIMAL product_width_cm
    }
    dim_date {
        VARCHAR date_key PK
        DATE full_date
        INTEGER year
        INTEGER quarter
        INTEGER month
        VARCHAR month_name
        INTEGER week_of_year
        INTEGER day_of_month
        VARCHAR day_name
        INTEGER day_of_week
        BOOLEAN is_weekend
        BOOLEAN is_weekday
    }
    dim_geolocation {
        VARCHAR zip_code_prefix PK
        DECIMAL centroid_lat
        DECIMAL centroid_lng
        VARCHAR city
        VARCHAR state
    }

    fact_order_items }o--|| dim_customers : "placed by"
    fact_order_items }o--|| dim_sellers : "fulfilled by"
    fact_order_items }o--|| dim_products : "contains"
    fact_order_items }o--|| dim_date : "purchased on"
    fact_orders }o--|| dim_customers : "placed by"
    fact_orders }o--|| dim_date : "purchased on"
    fact_payments }o--|| fact_orders : "payment for"