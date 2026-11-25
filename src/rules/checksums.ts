export function digitsOf(s: string): string {
  return s.replace(/\D/g, '')
}

export function luhn(digits: string): boolean {
  let sum = 0
  let double = false
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = digits.charCodeAt(i) - 48
    if (double) {
      d *= 2
      if (d > 9)
        d -= 9
    }
    sum += d
    double = !double
  }
  return sum % 10 === 0
}

const CN_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
const CN_ID_CHECK = '10X98765432'

/** GB 11643-1999 resident identity number, 18 characters. */
export function cnIdValid(id: string): boolean {
  if (!/^\d{17}[\dX]$/i.test(id))
    return false
  const y = +id.slice(6, 10)
  const m = +id.slice(10, 12)
  const d = +id.slice(12, 14)
  if (y < 1900 || y > 2099 || m < 1 || m > 12 || d < 1 || d > 31)
    return false
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate()
  if (d > days)
    return false
  let sum = 0
  for (let i = 0; i < 17; i++)
    sum += (id.charCodeAt(i) - 48) * CN_ID_WEIGHTS[i]!
  return CN_ID_CHECK[sum % 11] === id[17]!.toUpperCase()
}

/** Japanese individual number (My Number), 12 digits with check digit. */
export function myNumberValid(digits: string): boolean {
  if (!/^\d{12}$/.test(digits))
    return false
  let sum = 0
  for (let n = 1; n <= 11; n++) {
    const p = digits.charCodeAt(11 - n) - 48
    const q = n <= 6 ? n + 1 : n - 5
    sum += p * q
  }
  const r = sum % 11
  const check = r <= 1 ? 0 : 11 - r
  return check === digits.charCodeAt(11) - 48
}

export function myNumberCheckDigit(first11: string): number {
  let sum = 0
  for (let n = 1; n <= 11; n++)
    sum += (first11.charCodeAt(11 - n) - 48) * (n <= 6 ? n + 1 : n - 5)
  const r = sum % 11
  return r <= 1 ? 0 : 11 - r
}

export function ibanValid(raw: string): boolean {
  const s = raw.replace(/\s/g, '').toUpperCase()
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/.test(s))
    return false
  const r = s.slice(4) + s.slice(0, 4)
  let rem = 0
  for (const ch of r) {
    const v = ch >= 'A' ? String(ch.charCodeAt(0) - 55) : ch
    for (const c of v)
      rem = (rem * 10 + (c.charCodeAt(0) - 48)) % 97
  }
  return rem === 1
}

/** Major card networks by IIN prefix. */
export function cardPrefixOk(d: string): boolean {
  return /^(?:4|5[1-5]|2[2-7]|3[47]|3[05689]|6(?:011|5|4[4-9]|2))/.test(d)
}
