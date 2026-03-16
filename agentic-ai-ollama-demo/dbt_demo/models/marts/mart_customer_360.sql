{% if var('force_memory_error', false) %}
  {{ exceptions.raise_compiler_error('Simulated worker memory exhaustion while building mart_customer_360') }}
{% endif %}

with activity as (
    select * from {{ ref('fct_account_activity') }}
),
loans as (
    select
        customer_id,
        sum(principal_balance) as total_loan_balance,
        max(days_past_due) as max_days_past_due
    from {{ ref('stg_bank_loans') }}
    group by 1
)
select
    c.customer_id,
    c.customer_name,
    c.segment,
    c.risk_band,
    c.kyc_score,
    coalesce(sum(a.balance), 0) as total_deposit_balance,
    coalesce(sum(a.total_transaction_amount), 0) as total_transaction_amount,
    coalesce(sum(a.high_risk_txn_count), 0) as high_risk_txn_count,
    coalesce(l.total_loan_balance, 0) as total_loan_balance,
    coalesce(l.max_days_past_due, 0) as max_days_past_due
from {{ ref('stg_bank_customers') }} as c
left join activity as a
    on c.customer_id = a.customer_id
left join loans as l
    on c.customer_id = l.customer_id
group by 1, 2, 3, 4, 5, 9, 10
