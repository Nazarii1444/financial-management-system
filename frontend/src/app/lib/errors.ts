import { ApiError } from './api';
import type { Translations } from '../i18n/translations';

// Backend error texts (English) → translation lookup. Matched by substring, first hit wins.
const DETAIL_MAP: [string, (t: Translations) => string][] = [
  ['Invalid email or password', (t) => t.errors.invalidCredentials],
  ['Email already registered', (t) => t.errors.emailTaken],
  ['Email already taken', (t) => t.errors.emailTaken],
  ['Username already', (t) => t.errors.usernameTaken],
  ['same as current email', (t) => t.errors.sameEmail],
  ['Current password is incorrect', (t) => t.errors.wrongCurrentPassword],
  ['Invalid 2FA code', (t) => t.errors.invalid2fa],
  ['2FA session token', (t) => t.errors.twoFaSessionExpired],
  ['2FA is already enabled', (t) => t.errors.twoFaAlreadyEnabled],
  ['2FA is not enabled', (t) => t.errors.twoFaNotEnabled],
  ['User not found', (t) => t.errors.userNotFound],
  ['Member already exists', (t) => t.errors.memberExists],
  ['Personal budget cannot', (t) => t.errors.personalBudgetMembers],
  ['Only owner', (t) => t.errors.onlyOwner],
  ['Owner is already a member', (t) => t.errors.ownerAlreadyMember],
  ['Not a member', (t) => t.errors.forbidden],
  ['Forbidden', (t) => t.errors.forbidden],
  ['Goal is already completed', (t) => t.errors.goalCompleted],
  ['Goal is not completed', (t) => t.errors.goalNotCompleted],
  ['Cannot withdraw', (t) => t.errors.withdrawTooMuch],
  ['Target not reached', (t) => t.errors.targetNotReached],
  ['Already on Pro', (t) => t.errors.alreadyPro],
  ['Already on Free', (t) => t.errors.alreadyFree],
  ['Unsupported file type', (t) => t.errors.unsupportedFile],
  ['File is empty', (t) => t.errors.emptyFile],
  ['category', (t) => t.errors.invalidCategory],
  ['at least 8 characters', (t) => t.errors.password.minLength],
  ['uppercase letter', (t) => t.errors.password.uppercase],
  ['lowercase letter', (t) => t.errors.password.lowercase],
  ['contain a number', (t) => t.errors.password.number],
  ['special character', (t) => t.errors.password.special],
  ['too common', (t) => t.errors.password.common],
  ['leaked databases', (t) => t.errors.password.leaked],
];

function translateDetail(detail: string, t: Translations): string | null {
  // Password checks come joined with "; " from PATCH /auth/password
  const parts = detail.split(';').map((p) => p.trim()).filter(Boolean);
  const translated = parts.map((part) => DETAIL_MAP.find(([needle]) => part.includes(needle))?.[1](t));
  if (translated.every(Boolean)) return translated.join('. ');
  return null;
}

/** Human-readable, translated message for any error thrown by the API layer */
export function errorMessage(err: unknown, t: Translations): string {
  if (!(err instanceof ApiError)) return t.errors.generic;
  if (err.status === 0) return t.errors.network;
  if (err.status === 404 && err.detail === 'Not Found') return t.errors.notImplemented;
  if (err.status === 405) return t.errors.notImplemented;

  const { detail } = err;
  if (typeof detail === 'string') return translateDetail(detail, t) ?? detail;
  if (Array.isArray(detail)) {
    // Either a list of password errors (strings) or FastAPI validation errors
    if (detail.every((d) => typeof d === 'string')) {
      return translateDetail((detail as string[]).join('; '), t) ?? (detail as string[]).join('. ');
    }
    return t.errors.validation;
  }
  if (err.status === 401) return t.errors.sessionExpired;
  return t.errors.generic;
}
