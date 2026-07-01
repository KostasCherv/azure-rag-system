targetScope = 'resourceGroup'

param location string = resourceGroup().location
@minLength(3)
@maxLength(30)
param namePrefix string
param tenantId string
param apiImage string
param uiImage string
param backendAudience string
param backendClientId string
param apimAudience string
param apimScope string
param uiClientId string
param publisherName string
param publisherEmail string

param vnetAddressPrefix string = '10.40.0.0/16'
param containerAppsSubnetPrefix string = '10.40.0.0/23'
param apimSubnetPrefix string = '10.40.4.0/24'

param azureOpenAIEndpoint string
param azureOpenAIResourceName string
param azureOpenAIResourceGroupName string
param azureOpenAIChatDeployment string
param azureOpenAIEmbeddingDeployment string
param searchEndpoint string
param searchServiceName string
param searchResourceGroupName string
param searchLocation string = location
param searchIndex string
param searchSku string = 'standard'
param searchReplicaCount int = 1
param searchPartitionCount int = 1
@allowed(['Enabled', 'Disabled'])
param searchPublicNetworkAccess string = 'Enabled'
param storageAccountUrl string
param storageAccountName string
param storageResourceGroupName string
param storageContainer string
param storageResourceId string

module network 'modules/network.bicep' = {
  name: 'network'
  params: {
    location: location
    namePrefix: namePrefix
    vnetAddressPrefix: vnetAddressPrefix
    containerAppsSubnetPrefix: containerAppsSubnetPrefix
    apimSubnetPrefix: apimSubnetPrefix
  }
}

module searchIdentity 'modules/search-identity.bicep' = {
  name: 'search-identity'
  scope: resourceGroup(searchResourceGroupName)
  params: {
    location: searchLocation
    searchServiceName: searchServiceName
    searchSku: searchSku
    replicaCount: searchReplicaCount
    partitionCount: searchPartitionCount
    publicNetworkAccess: searchPublicNetworkAccess
  }
}

module apimService 'modules/apim-service.bicep' = {
  name: 'apim-service'
  params: {
    location: location
    namePrefix: namePrefix
    apimSubnetId: network.outputs.apimSubnetId
    publisherName: publisherName
    publisherEmail: publisherEmail
  }
}

module apps 'modules/container-apps.bicep' = {
  name: 'container-apps'
  params: {
    location: location
    namePrefix: namePrefix
    internalSubnetId: network.outputs.containerAppsSubnetId
    apiImage: apiImage
    uiImage: uiImage
    backendAudience: backendAudience
    backendClientId: backendClientId
    tenantId: tenantId
    apimPrincipalId: apimService.outputs.principalId
    apimGatewayUrl: apimService.outputs.gatewayUrl
    apimScope: apimScope
    azureOpenAIEndpoint: azureOpenAIEndpoint
    azureOpenAIChatDeployment: azureOpenAIChatDeployment
    azureOpenAIEmbeddingDeployment: azureOpenAIEmbeddingDeployment
    searchEndpoint: searchEndpoint
    searchIndex: searchIndex
    storageAccountUrl: storageAccountUrl
    storageContainer: storageContainer
    storageResourceId: storageResourceId
  }
}

module privateDns 'modules/private-dns.bicep' = {
  name: 'private-dns'
  params: {
    namePrefix: namePrefix
    vnetId: network.outputs.vnetId
    zoneName: apps.outputs.internalEnvironmentDomain
    staticIp: apps.outputs.internalEnvironmentStaticIp
  }
}

module apimApi 'modules/apim.bicep' = {
  name: 'apim-api'
  params: {
    apimName: apimService.outputs.name
    backendFqdn: apps.outputs.apiFqdn
    backendAudience: backendAudience
    tenantId: tenantId
    apimAudience: apimAudience
    uiPrincipalId: apps.outputs.uiPrincipalId
    uiClientId: uiClientId
  }
}

module openAIRbac 'modules/rbac-openai.bicep' = {
  name: 'rbac-openai'
  scope: resourceGroup(azureOpenAIResourceGroupName)
  params: {
    principalIds: [apps.outputs.apiPrincipalId, searchIdentity.outputs.principalId]
    resourceName: azureOpenAIResourceName
  }
}

module searchRbac 'modules/rbac-search.bicep' = {
  name: 'rbac-search'
  scope: resourceGroup(searchResourceGroupName)
  params: {
    principalId: apps.outputs.apiPrincipalId
    resourceName: searchServiceName
  }
}

module storageRbac 'modules/rbac-storage.bicep' = {
  name: 'rbac-storage'
  scope: resourceGroup(storageResourceGroupName)
  params: {
    apiPrincipalId: apps.outputs.apiPrincipalId
    searchPrincipalId: searchIdentity.outputs.principalId
    resourceName: storageAccountName
  }
}

output uiUrl string = 'https://${apps.outputs.uiFqdn}'
output apimGatewayUrl string = apimService.outputs.gatewayUrl
output apiPrivateFqdn string = apps.outputs.apiFqdn
