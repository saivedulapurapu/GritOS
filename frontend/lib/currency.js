// Matches backend schemas.CURRENCY_SYMBOLS
export const CURRENCY_SYMBOLS = { INR: '₹', USD: '$' };

export const currencySymbol = (currency) => CURRENCY_SYMBOLS[currency] || '';
