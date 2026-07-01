param principalId string
param resourceName string
var searchIndexDataReader = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
resource target 'Microsoft.Search/searchServices@2025-05-01' existing = { name: resourceName }
resource assignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(target.id, principalId, searchIndexDataReader)
  scope: target
  properties: { principalId: principalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReader) }
}
