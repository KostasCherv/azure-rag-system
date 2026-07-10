param location string
@minLength(3)
@maxLength(10)
param namePrefix string
param storageContainer string
param searchIndex string
param chatDeploymentName string
param embeddingDeploymentName string
param setupPrincipalId string
param setupPrincipalType string

@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param acrSku string = 'Basic'

@allowed([
  'free'
  'basic'
  'standard'
  'standard2'
  'standard3'
  'storage_optimized_l1'
  'storage_optimized_l2'
])
param searchSku string = 'basic'

param searchReplicaCount int = 1
param searchPartitionCount int = 1

param chatModelName string
param chatModelVersion string
param chatDeploymentSkuName string
param chatDeploymentCapacity int = 10

param embeddingModelName string
param embeddingModelVersion string
param embeddingDeploymentSkuName string
param embeddingDeploymentCapacity int = 10

var suffix = uniqueString(resourceGroup().id, namePrefix)
var storageName = '${namePrefix}${suffix}'
var acrName = '${namePrefix}acr${suffix}'
var searchName = '${namePrefix}-search-${suffix}'
var openAIName = '${namePrefix}-openai-${suffix}'

var cognitiveServicesOpenAIUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var searchServiceContributor = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
var searchIndexDataContributor = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var storageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: acrSku
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: storageContainer
  properties: {
    publicAccess: 'None'
  }
}

resource openAI 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: openAIName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openAIName
    publicNetworkAccess: 'Enabled'
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAI
  name: chatDeploymentName
  sku: {
    name: chatDeploymentSkuName
    capacity: chatDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: chatModelName
      version: chatModelVersion
    }
    raiPolicyName: 'Microsoft.Default'
  }
  dependsOn: [
    embeddingDeployment
  ]
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAI
  name: embeddingDeploymentName
  sku: {
    name: embeddingDeploymentSkuName
    capacity: embeddingDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
    raiPolicyName: 'Microsoft.Default'
  }
}

resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: searchName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: searchSku
  }
  properties: {
    replicaCount: searchReplicaCount
    partitionCount: searchPartitionCount
    hostingMode: 'Default'
    publicNetworkAccess: 'enabled'
    disableLocalAuth: true
  }
}

resource setupSearchAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(setupPrincipalId)) {
  name: guid(search.id, setupPrincipalId, searchServiceContributor)
  scope: search
  properties: {
    principalId: setupPrincipalId
    principalType: setupPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributor)
  }
}

resource setupSearchIndexAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(setupPrincipalId)) {
  name: guid(search.id, setupPrincipalId, searchIndexDataContributor)
  scope: search
  properties: {
    principalId: setupPrincipalId
    principalType: setupPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataContributor)
  }
}

resource setupStorageAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(setupPrincipalId)) {
  name: guid(storage.id, setupPrincipalId, storageBlobDataContributor)
  scope: storage
  properties: {
    principalId: setupPrincipalId
    principalType: setupPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributor)
  }
}

resource setupOpenAIAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(setupPrincipalId)) {
  name: guid(openAI.id, setupPrincipalId, cognitiveServicesOpenAIUser)
  scope: openAI
  properties: {
    principalId: setupPrincipalId
    principalType: setupPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAIUser)
  }
  dependsOn: [
    chatDeployment
    embeddingDeployment
  ]
}

output containerRegistryName string = acr.name
output containerRegistryLoginServer string = acr.properties.loginServer
output azureOpenAIEndpoint string = 'https://${openAI.name}.openai.azure.com'
output azureOpenAIResourceName string = openAI.name
output azureOpenAIChatDeployment string = chatDeployment.name
output azureOpenAIEmbeddingDeployment string = embeddingDeployment.name
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output searchServiceName string = search.name
output searchIndex string = searchIndex
output storageAccountUrl string = storage.properties.primaryEndpoints.blob
output storageAccountName string = storage.name
output storageContainer string = container.name
output storageResourceId string = storage.id
