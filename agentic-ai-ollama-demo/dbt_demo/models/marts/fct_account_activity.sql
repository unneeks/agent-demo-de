select
    a.account_id,
    a.customer_id,
    a.product_type,
    a.balance,
    count(t.transaction_id) as transaction_count,
    sum(t.amount) as total_transaction_amount,
    sum(case when t.is_high_risk then 1 else 0 end) as high_risk_txn_count
from {{ ref('stg_bank_accounts') }} as a
left join {{ ref('stg_bank_transactions') }} as t
    on a.account_id = t.account_id
group by 1, 2, 3, 4
