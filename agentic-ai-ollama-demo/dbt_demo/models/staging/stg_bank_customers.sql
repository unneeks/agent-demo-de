select
    cast(customer_id as integer) as customer_id,
    customer_name,
    segment,
    risk_band,
    cast(kyc_score as double) as kyc_score
from {{ ref('bank_customers') }}
