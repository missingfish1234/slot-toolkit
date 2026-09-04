'use strict';

const assert = require('assert');
const { ease, formatValue } = require('../dist/shared');

assert.strictEqual(formatValue(1234.5, { decimals: 2, thousands: true }), '1,234.50');
assert.strictEqual(formatValue(1234567, { decimals: 2, compact: true, prefix: '$' }), '$1.23M');
assert.strictEqual(formatValue(-12, { decimals: 0, prefix: '[', suffix: ']' }), '[-12]');
assert.strictEqual(ease('linear', 0.25), 0.25);
assert.strictEqual(ease('ease-out', 1), 1);
assert.strictEqual(ease('ease-in', -1), 0);

console.log('rolling-score-tester core tests passed');
