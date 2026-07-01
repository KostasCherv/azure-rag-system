# Contoso Analytics Product Notes

Contoso Analytics helps operations teams monitor support queues, incident
response times, and customer satisfaction trends. The product stores raw event
data, computes daily aggregates, and exposes dashboards for team leads.

The ingestion service accepts JSON events over HTTPS. Events that fail schema
validation are rejected with a 400 response and are not stored. Customers can
create custom dashboard filters for region, product line, account segment, and
incident severity.

Data freshness targets are fifteen minutes for dashboards and five minutes for
incident alerting workflows.

