# N+1 Query Analysis

## Summary
There are 999 N+1 queries occurring in the django-bulk-triggers framework. The queries are happening during trigger execution, NOT during the bulk_create upsert operation as initially suspected.

## Query Pattern
For each DailyFinancialAggregate record, the following queries are executed:
1. Query for `monthly_financial_aggregates_monthlyfinancialaggregate` (e.g., WHERE id = 8)
2. Query for `users_user` WHERE id = 1 (created_by)
3. Query for `users_user` WHERE id = 1 (updated_by)
4. Query for `augend_financial_accounts_financialaccount` WHERE id = 1

This pattern repeats for EACH record, indicating that the code is accessing the `monthly_financial_aggregate` relationship in a loop, and then accessing its foreign key relationships (`created_by`, `updated_by`, `financial_account`).

## Root Cause
The N+1 queries are happening because:
1. DailyFinancialAggregate objects are being processed in a loop during trigger execution
2. Each object accesses its `monthly_financial_aggregate` relationship
3. The `monthly_financial_aggreg ate` objects were NOT loaded with `select_related` to preload their own foreign keys
4. When the trigger code accesses fields like `monthly_financial_aggregate.created_by`, `monthly_financial_aggregate.updated_by`, or `monthly_financial_aggregate.financial_account`, it triggers additional queries

## Location
The N+1 queries appear to be happening during trigger execution, specifically when triggers access related objects. The queries start appearing around line 485 in the console output log, which is after the bulk_create operation has completed.

## Fix Required
The fix needs to be applied in the trigger execution path, where DailyFinancialAggregate records are being processed. The solution is to:
1. Identify where DailyFinancialAggregate records are being loaded for trigger execution
2. Add `select_related` to preload the `monthly_financial_aggregate` relationship
3. Also use nested `select_related` to preload the foreign keys of `monthly_financial_aggregate` (created_by, updated_by, financial_account)

## Debug Findings
- The fix I added to `bulk_operations.py` line 127-161 is NOT being executed (debug messages don't appear in logs)
- This confirms that the N+1 queries are NOT happening during the bulk_create upsert operation
- The queries are happening AFTER the bulk_create operation, during trigger execution
- The specific trigger that's causing the N+1 queries needs to be identified

## Next Steps
1. Identify which trigger is accessing `monthly_financial_aggregate` relationship
2. Find where DailyFinancialAggregate records are loaded for that trigger
3. Add proper `select_related` with nested relationships to prevent N+1 queries

