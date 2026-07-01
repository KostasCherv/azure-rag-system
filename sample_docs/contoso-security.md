# Contoso Security Overview

Contoso encrypts customer data in transit with TLS 1.2 or later and encrypts
data at rest with platform-managed keys by default. Enterprise customers can
request customer-managed keys for selected storage workloads.

Administrative access is reviewed monthly. Privileged access requires
multi-factor authentication and is logged in the central audit workspace.
Audit logs are retained for 365 days unless a customer contract requires a
longer retention period.

Contoso recommends single sign-on with Microsoft Entra ID for production
tenants. Local administrator accounts should be break-glass accounts only.

