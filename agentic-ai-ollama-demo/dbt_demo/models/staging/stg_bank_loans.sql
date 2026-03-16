select
    cast(loan_id as integer) as loan_id,
    cast(customer_id as integer) as customer_id,
    loan_type,
    cast(principal_balance as double) as principal_balance,
    cast(days_past_due as integer) as days_past_due
from {{ ref('bank_loans') }}
