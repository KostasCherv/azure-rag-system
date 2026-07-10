param apimName string
param backendFqdn string
param backendAudience string
param tenantId string
param apimAudience string
param uiPrincipalId string
param uiClientId string

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
}

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'rag'
  properties: {
    displayName: 'Secure RAG API'
    path: 'rag'
    protocols: ['https']
    serviceUrl: 'https://${backendFqdn}'
    subscriptionRequired: false
  }
}

resource agui 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'agui'
  properties: { displayName: 'AG-UI', method: 'POST', urlTemplate: '/agui' }
}

resource ready 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'ready'
  properties: { displayName: 'Readiness', method: 'GET', urlTemplate: '/ready' }
}

resource corpusList 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'corpus-list'
  properties: { displayName: 'Corpus list', method: 'GET', urlTemplate: '/corpus/documents' }
}

resource corpusUpload 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'corpus-upload'
  properties: { displayName: 'Corpus upload', method: 'POST', urlTemplate: '/corpus/documents' }
}

resource corpusDelete 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'corpus-delete'
  properties: {
    displayName: 'Corpus delete'
    method: 'DELETE'
    urlTemplate: '/corpus/documents/{name}'
    templateParameters: [
      {
        name: 'name'
        type: 'string'
        required: true
      }
    ]
  }
}

resource corpusRun 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'corpus-run'
  properties: { displayName: 'Corpus indexer run', method: 'POST', urlTemplate: '/corpus/indexer/run' }
}

resource corpusStatus 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'corpus-status'
  properties: { displayName: 'Corpus indexer status', method: 'GET', urlTemplate: '/corpus/indexer' }
}

var rawPolicy = loadTextContent('../policies/api-policy.xml')
var tenantPolicy = replace(rawPolicy, '{{tenantId}}', tenantId)
var audiencePolicy = replace(tenantPolicy, '{{apimAudience}}', apimAudience)
var apimClientIdPolicy = replace(audiencePolicy, '{{apimClientId}}', replace(apimAudience, 'api://', ''))
var uiPrincipalPolicy = replace(apimClientIdPolicy, '{{uiPrincipalId}}', uiPrincipalId)
var uiClientPolicy = replace(uiPrincipalPolicy, '{{uiClientId}}', uiClientId)
var backendFqdnPolicy = replace(uiClientPolicy, '{{backendFqdn}}', backendFqdn)
var renderedPolicy = replace(backendFqdnPolicy, '{{backendAudience}}', backendAudience)

resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: renderedPolicy
  }
  dependsOn: [agui, ready, corpusList, corpusUpload, corpusDelete, corpusRun, corpusStatus]
}
