targetScope = 'subscription'

@description('Azure region for the resource group and all bootstrap resources.')
param location string = deployment().location

@description('Resource group that will contain greenfield RAG prerequisites.')
param resourceGroupName string

@minLength(3)
@maxLength(10)
@description('Lowercase letters and digits only. Used for globally unique service names.')
param namePrefix string

@description('Name of the Blob container used as the Azure AI Search data source.')
param storageContainer string = 'sample-docs'

@description('Azure AI Search index name that setup_azure_rag.py will create or update.')
param searchIndex string = 'rag-live-test-index'

@description('Chat model deployment name used by the API.')
param chatDeploymentName string = 'rag-chat'

@description('Embedding model deployment name used by Azure AI Search vectorization.')
param embeddingDeploymentName string = 'rag-embedding'

@description('Azure OpenAI chat model name. Availability depends on region and subscription quota.')
param chatModelName string = 'gpt-5.1'

@description('Azure OpenAI chat model version.')
param chatModelVersion string = '2025-11-13'

@description('Azure OpenAI chat deployment SKU. GlobalStandard is often required for globally routed models.')
param chatDeploymentSkuName string = 'GlobalStandard'

@description('Azure OpenAI embedding model name.')
param embeddingModelName string = 'text-embedding-3-small'

@description('Azure OpenAI embedding model version.')
param embeddingModelVersion string = '1'

@description('Azure OpenAI embedding deployment SKU.')
param embeddingDeploymentSkuName string = 'Standard'

@description('Embedding deployment capacity in thousands of tokens per minute. Indexing throughput is bounded by this.')
param embeddingDeploymentCapacity int = 200

@description('Optional principal object ID for the identity that will run scripts/setup_azure_rag.py.')
param setupPrincipalId string = ''

@allowed([
  'User'
  'ServicePrincipal'
  'Group'
])
@description('Principal type for setupPrincipalId.')
param setupPrincipalType string = 'User'

resource rg 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: resourceGroupName
  location: location
}

module resources 'modules/bootstrap-resources.bicep' = {
  name: 'rag-bootstrap-resources'
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    storageContainer: storageContainer
    searchIndex: searchIndex
    chatDeploymentName: chatDeploymentName
    embeddingDeploymentName: embeddingDeploymentName
    chatModelName: chatModelName
    chatModelVersion: chatModelVersion
    chatDeploymentSkuName: chatDeploymentSkuName
    embeddingModelName: embeddingModelName
    embeddingModelVersion: embeddingModelVersion
    embeddingDeploymentSkuName: embeddingDeploymentSkuName
    embeddingDeploymentCapacity: embeddingDeploymentCapacity
    setupPrincipalId: setupPrincipalId
    setupPrincipalType: setupPrincipalType
  }
}

output resourceGroupName string = rg.name
output containerRegistryName string = resources.outputs.containerRegistryName
output containerRegistryLoginServer string = resources.outputs.containerRegistryLoginServer
output azureOpenAIEndpoint string = resources.outputs.azureOpenAIEndpoint
output azureOpenAIResourceName string = resources.outputs.azureOpenAIResourceName
output azureOpenAIChatDeployment string = resources.outputs.azureOpenAIChatDeployment
output azureOpenAIEmbeddingDeployment string = resources.outputs.azureOpenAIEmbeddingDeployment
output searchEndpoint string = resources.outputs.searchEndpoint
output searchServiceName string = resources.outputs.searchServiceName
output searchIndex string = resources.outputs.searchIndex
output storageAccountUrl string = resources.outputs.storageAccountUrl
output storageAccountName string = resources.outputs.storageAccountName
output storageContainer string = resources.outputs.storageContainer
output storageResourceId string = resources.outputs.storageResourceId
