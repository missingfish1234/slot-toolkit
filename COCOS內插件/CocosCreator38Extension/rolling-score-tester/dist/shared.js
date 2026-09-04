'use strict';

function finite(value, fallback = 0) {
    const result = Number(value);
    return Number.isFinite(result) ? result : fallback;
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function ease(name, progress) {
    const t = clamp(finite(progress), 0, 1);
    switch (name) {
        case 'ease-in': return t * t * t;
        case 'ease-in-out': return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        case 'ease-out': return 1 - Math.pow(1 - t, 3);
        default: return t;
    }
}

function compactNumber(value, decimals) {
    const absolute = Math.abs(value);
    const units = [
        { value: 1e12, suffix: 'T' },
        { value: 1e9, suffix: 'B' },
        { value: 1e6, suffix: 'M' },
        { value: 1e3, suffix: 'K' }
    ];
    const unit = units.find((item) => absolute >= item.value);
    if (!unit) return { value, suffix: '' };
    return { value: value / unit.value, suffix: unit.suffix };
}

function formatValue(value, options = {}) {
    const decimals = clamp(Math.trunc(finite(options.decimals, 0)), 0, 8);
    const compact = options.compact ? compactNumber(finite(value), decimals) : { value: finite(value), suffix: '' };
    const fixed = compact.value.toFixed(decimals);
    const parts = fixed.split('.');
    if (options.thousands) parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    const numberText = parts.join('.');
    return `${options.prefix || ''}${numberText}${compact.suffix}${options.suffix || ''}`;
}

module.exports = { clamp, ease, finite, formatValue };
