/**
 * Browser side of passkeys (WebAuthn). The server sends options as JSON with
 * base64url strings; navigator.credentials wants ArrayBuffers, and its result
 * has to go back as JSON. Same shapes as PublicKeyCredential.toJSON().
 */

type Json = Record<string, unknown>;

export class PasskeyCancelled extends Error {}
export class PasskeyUnsupported extends Error {}

export const passkeysSupported = (): boolean =>
  typeof window !== 'undefined' && typeof window.PublicKeyCredential === 'function' && Boolean(navigator.credentials);

function fromB64url(value: string): ArrayBuffer {
  const b64 = value.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(value.length / 4) * 4, '=');
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

function toB64url(buffer: ArrayBuffer | null | undefined): string | null {
  if (!buffer) return null;
  const bytes = new Uint8Array(buffer);
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

const descriptors = (list: unknown) =>
  ((list as Json[] | undefined) ?? []).map((c) => ({ ...c, id: fromB64url(c.id as string) })) as PublicKeyCredentialDescriptor[];

function rethrow(err: unknown): never {
  // NotAllowedError: the user closed the prompt or it timed out — not worth an error toast
  if (err instanceof DOMException && (err.name === 'NotAllowedError' || err.name === 'AbortError')) throw new PasskeyCancelled();
  throw err;
}

/** navigator.credentials.create() for server-made creation options → JSON for POST /passkeys/register */
export async function createPasskey(options: Json): Promise<Json> {
  if (!passkeysSupported()) throw new PasskeyUnsupported();
  const user = options.user as Json;
  const publicKey = {
    ...options,
    challenge: fromB64url(options.challenge as string),
    user: { ...user, id: fromB64url(user.id as string) },
    excludeCredentials: descriptors(options.excludeCredentials),
  } as unknown as PublicKeyCredentialCreationOptions;
  let credential: PublicKeyCredential;
  try {
    credential = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential;
  } catch (err) {
    rethrow(err);
  }
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: toB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toB64url(response.clientDataJSON),
      attestationObject: toB64url(response.attestationObject),
      transports: typeof response.getTransports === 'function' ? response.getTransports() : [],
    },
    clientExtensionResults: credential.getClientExtensionResults(),
    authenticatorAttachment: credential.authenticatorAttachment ?? null,
  };
}

/** navigator.credentials.get() for server-made request options → JSON for POST /passkeys/login */
export async function getPasskey(options: Json): Promise<Json> {
  if (!passkeysSupported()) throw new PasskeyUnsupported();
  const publicKey = {
    ...options,
    challenge: fromB64url(options.challenge as string),
    allowCredentials: descriptors(options.allowCredentials),
  } as unknown as PublicKeyCredentialRequestOptions;
  let credential: PublicKeyCredential;
  try {
    credential = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential;
  } catch (err) {
    rethrow(err);
  }
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: toB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toB64url(response.clientDataJSON),
      authenticatorData: toB64url(response.authenticatorData),
      signature: toB64url(response.signature),
      userHandle: toB64url(response.userHandle),
    },
    clientExtensionResults: credential.getClientExtensionResults(),
    authenticatorAttachment: credential.authenticatorAttachment ?? null,
  };
}

/** A friendly default name for a new passkey: "Chrome · Windows" */
export function defaultPasskeyName(): string {
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua) ? 'Edge' : /OPR\//.test(ua) ? 'Opera' : /Firefox\//.test(ua) ? 'Firefox'
    : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
  const os = /iPhone|iPad/.test(ua) ? 'iOS' : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows'
    : /Mac OS X/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : '';
  return os ? `${browser} · ${os}` : browser;
}
