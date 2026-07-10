param principalIds array
param resourceName string

var acrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource target 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: resourceName
}

resource assignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalId in principalIds: {
  name: guid(target.id, principalId, acrPull)
  scope: target
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull)
  }
}]
