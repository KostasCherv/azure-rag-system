param location string
param searchServiceName string
param searchSku string
param replicaCount int
param partitionCount int
param publicNetworkAccess string

resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: searchServiceName
  location: location
  identity: { type: 'SystemAssigned' }
  sku: { name: searchSku }
  properties: {
    replicaCount: replicaCount
    partitionCount: partitionCount
    publicNetworkAccess: publicNetworkAccess
  }
}

output principalId string = search.identity.principalId
