param principalIds array
param resourceName string
var cognitiveServicesOpenAIUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
resource target 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = { name: resourceName }
resource assignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalId in principalIds: {
  name: guid(target.id, principalId, cognitiveServicesOpenAIUser)
  scope: target
  properties: { principalId: principalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAIUser) }
}]
