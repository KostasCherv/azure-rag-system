param location string
param publicLocation string = location
param namePrefix string
param internalSubnetId string
param apiImage string
param uiImage string
param useSingleEnvironment bool = false
param registryServer string = ''
param registryIdentityId string = ''
param backendAudience string
param backendClientId string
param tenantId string
param apimPrincipalId string
param apimGatewayUrl string
param apimScope string
param azureOpenAIEndpoint string
param azureOpenAIChatDeployment string
param azureOpenAIEmbeddingDeployment string
param searchEndpoint string
param searchIndex string
param storageAccountUrl string
param storageContainer string
param storageResourceId string
param applicationInsightsConnectionString string
param cosmosEndpoint string
param uiUserAuthClientId string

resource internalEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = if (!useSingleEnvironment) {
  name: '${namePrefix}-api-env'
  location: location
  properties: {
    vnetConfiguration: {
      infrastructureSubnetId: internalSubnetId
      internal: true
    }
    zoneRedundant: false
  }
}

resource publicEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-ui-env'
  location: publicLocation
  properties: {
    vnetConfiguration: {
      internal: false
    }
    zoneRedundant: false
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-api'
  location: useSingleEnvironment ? publicLocation : location
  identity: empty(registryIdentityId) ? {
    type: 'SystemAssigned'
  } : {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${registryIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: useSingleEnvironment ? publicEnvironment.id : internalEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: empty(registryServer) ? [] : [
        {
          server: registryServer
          identity: registryIdentityId
        }
      ]
      ingress: {
        // The environment load balancer is internal, so this exposes the app only to the VNet.
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          env: [
            { name: 'PORT', value: '8000' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAIEndpoint }
            { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: azureOpenAIChatDeployment }
            { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: azureOpenAIEmbeddingDeployment }
            { name: 'AZURE_SEARCH_ENDPOINT', value: searchEndpoint }
            { name: 'AZURE_SEARCH_INDEX', value: searchIndex }
            { name: 'AZURE_STORAGE_ACCOUNT_URL', value: storageAccountUrl }
            { name: 'AZURE_STORAGE_CONTAINER', value: storageContainer }
            { name: 'AZURE_STORAGE_RESOURCE_ID', value: storageResourceId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: applicationInsightsConnectionString }
            { name: 'AZURE_COSMOS_ENDPOINT', value: cosmosEndpoint }
            { name: 'AZURE_COSMOS_DATABASE', value: 'rag' }
            { name: 'AZURE_COSMOS_SESSIONS_CONTAINER', value: 'sessions' }
            { name: 'SESSION_LOCAL_USER_ID', value: '' }
          ]
          resources: { cpu: json('0.5'), memory: '1Gi' }
          probes: [
            { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 10, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 5, periodSeconds: 10 }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 10 }
    }
  }
}

resource apiAuth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = {
  parent: api
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      unauthenticatedClientAction: 'Return401'
      excludedPaths: ['/health']
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: backendClientId
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [backendAudience]
          defaultAuthorizationPolicy: {
            allowedPrincipals: {
              identities: [apimPrincipalId]
            }
          }
        }
      }
    }
  }
}

resource ui 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-ui'
  location: publicLocation
  identity: empty(registryIdentityId) ? {
    type: 'SystemAssigned'
  } : {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${registryIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: publicEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: empty(registryServer) ? [] : [
        {
          server: registryServer
          identity: registryIdentityId
        }
      ]
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'ui'
          image: uiImage
          env: [
            { name: 'PORT', value: '3000' }
            { name: 'AGENT_URL', value: '${apimGatewayUrl}/rag/agui' }
            { name: 'READY_URL', value: '${apimGatewayUrl}/rag/ready' }
            { name: 'APIM_SCOPE', value: apimScope }
            { name: 'REQUIRE_USER_AUTH', value: 'true' }
          ]
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 10 }
    }
  }
}

resource uiAuth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = {
  parent: ui
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: uiUserAuthClientId
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenantId}/v2.0'
        }
        login: {
          loginParameters: ['prompt=select_account']
        }
      }
    }
  }
}

output apiPrincipalId string = api.identity.principalId
output uiPrincipalId string = ui.identity.principalId
output apiFqdn string = api.properties.configuration.ingress.fqdn
output uiFqdn string = ui.properties.configuration.ingress.fqdn
output internalEnvironmentDomain string = internalEnvironment.?properties.defaultDomain ?? ''
output internalEnvironmentStaticIp string = internalEnvironment.?properties.staticIp ?? ''
