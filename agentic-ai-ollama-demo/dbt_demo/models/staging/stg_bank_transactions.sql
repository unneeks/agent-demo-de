select
    cast(transaction_id as integer) as transaction_id,
    cast(account_id as integer) as account_id,
    cast(txn_ts as timestamp) as txn_ts,
    txn_type,
    cast(amount as double) as amount,
    merchant_category,
    cast(is_high_risk as boolean) as is_high_risk
from {{ ref('bank_transactions') }}
