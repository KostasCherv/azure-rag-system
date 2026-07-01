import "server-only";
import { DefaultAzureCredential } from "@azure/identity";

type Credential = { getToken(scope: string): Promise<{ token: string } | null> };

export function getApimScope(): string {
  const scope = process.env.APIM_SCOPE;
  if (!scope?.endsWith("/.default")) throw new Error("APIM_SCOPE must end with /.default");
  return scope;
}

export function createTokenProvider(credential: Credential = new DefaultAzureCredential()) {
  return async (): Promise<string> => {
    const result = await credential.getToken(getApimScope());
    if (!result?.token) throw new Error("APIM access token unavailable");
    return result.token;
  };
}

export const getApimToken = createTokenProvider();
