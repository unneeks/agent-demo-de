select
    cast(account_id as integer) as account_id,
    cast(customer_id as integer) as customer_id,
    product_type,
    cast(balance as double) as balance,
    status
from {{ ref('bank_accounts') }}
