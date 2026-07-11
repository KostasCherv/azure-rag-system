targetScope = 'resourceGroup'

param location string = resourceGroup().location
param publicContainerAppsLocation string = 'swedencentral'
@minLength(3)
@maxLength(28)
@description('Lowercase letters, digits, and internal hyphens only; must start with a letter and end with a letter or digit.')
param namePrefix string
param tenantId string
param apiImage string
param uiImage string
param useSingleContainerAppsEnvironment bool = false
param containerRegistryLoginServer string = ''
param containerRegistryName string = ''
param containerRegistryResourceGroupName string = ''
param backendAudience string
param backendClientId string
param apimAudience string
param apimScope string
param uiClientId string
param uiUserAuthClientId string
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
param searchIndex string
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

resource existingSearch 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchServiceName
  scope: resourceGroup(searchResourceGroupName)
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-07-01' = {
  name: '${namePrefix}-logs'
  location: location
  properties: {
    retentionInDays: 30
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-appi'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: '${namePrefix}-cosmos'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [{ locationName: location, failoverPriority: 0, isZoneRedundant: false }]
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
    capabilities: [{ name: 'EnableServerless' }]
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: cosmos
  name: 'rag'
  properties: { resource: { id: 'rag' } }
}

resource sessionsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: cosmosDatabase
  name: 'sessions'
  properties: {
    resource: {
      id: 'sessions'
      partitionKey: { paths: ['/userId'], kind: 'Hash', version: 2 }
      defaultTtl: 7776000
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [{ path: '/userId/?' }, { path: '/updatedAt/?' }]
        excludedPaths: [{ path: '/messages/*' }]
      }
    }
  }
}

resource acrPullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = if (!empty(containerRegistryName)) {
  name: '${namePrefix}-acr-pull'
  location: location
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

module acrRbac 'modules/rbac-acr.bicep' = if (!empty(containerRegistryName)) {
  name: 'rbac-acr'
  scope: resourceGroup(empty(containerRegistryResourceGroupName) ? resourceGroup().name : containerRegistryResourceGroupName)
  params: {
    principalIds: [acrPullIdentity.?properties.principalId ?? '']
    resourceName: containerRegistryName
  }
}

module apps 'modules/container-apps.bicep' = {
  name: 'container-apps'
  params: {
    location: location
    publicLocation: publicContainerAppsLocation
    namePrefix: namePrefix
    internalSubnetId: network.outputs.containerAppsSubnetId
    apiImage: apiImage
    uiImage: uiImage
    useSingleEnvironment: useSingleContainerAppsEnvironment
    registryServer: containerRegistryLoginServer
    registryIdentityId: !empty(containerRegistryName) ? acrPullIdentity.id : ''
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
    applicationInsightsConnectionString: applicationInsights.properties.ConnectionString
    cosmosEndpoint: cosmos.properties.documentEndpoint
    uiUserAuthClientId: uiUserAuthClientId
  }
  dependsOn: [
    acrRbac
  ]
}

resource cosmosDataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, '${namePrefix}-api', 'cosmos-data-contributor')
  properties: {
    principalId: apps.outputs.apiPrincipalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: cosmos.id
  }
}

module privateDns 'modules/private-dns.bicep' = if (!useSingleContainerAppsEnvironment) {
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
    principalIds: [apps.outputs.apiPrincipalId, existingSearch.identity.principalId]
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
    searchPrincipalId: existingSearch.identity.principalId
    resourceName: storageAccountName
  }
}

output uiUrl string = 'https://${apps.outputs.uiFqdn}'
output apimGatewayUrl string = apimService.outputs.gatewayUrl
output apiPrivateFqdn string = apps.outputs.apiFqdn
output uiPrincipalId string = apps.outputs.uiPrincipalId
output apiPrincipalId string = apps.outputs.apiPrincipalId
output apimPrincipalId string = apimService.outputs.principalId
