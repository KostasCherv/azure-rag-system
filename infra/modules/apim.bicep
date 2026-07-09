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

var rawPolicy = loadTextContent('../policies/api-policy.xml')
var tenantPolicy = replace(rawPolicy, '{{tenantId}}', tenantId)
var audiencePolicy = replace(tenantPolicy, '{{apimAudience}}', apimAudience)
var uiPrincipalPolicy = replace(audiencePolicy, '{{uiPrincipalId}}', uiPrincipalId)
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
  dependsOn: [agui, ready]
}
