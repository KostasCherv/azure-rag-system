param apiPrincipalId string
param searchPrincipalId string
param resourceName string
var storageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var storageBlobDataReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
resource target 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: resourceName }
resource apiAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(target.id, apiPrincipalId, storageBlobDataContributor)
  scope: target
  properties: { principalId: apiPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributor) }
}
resource searchAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(target.id, searchPrincipalId, storageBlobDataReader)
  scope: target
  properties: { principalId: searchPrincipalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReader) }
}
