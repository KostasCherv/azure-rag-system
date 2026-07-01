param principalId string
param resourceName string
var searchIndexDataReader = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
var searchServiceContributor = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
resource target 'Microsoft.Search/searchServices@2025-05-01' existing = { name: resourceName }
resource indexReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(target.id, principalId, searchIndexDataReader)
  scope: target
  properties: { principalId: principalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReader) }
}

// GET /indexers/{name}/status is a Search management operation used by /ready.
resource serviceContributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(target.id, principalId, searchServiceContributor)
  scope: target
  properties: { principalId: principalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributor) }
}
