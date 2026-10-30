/* Minimal Tailwind CDN fallback - just defines tailwind object */
window.tailwind = window.tailwind || {
  config: function() {},
  version: 'fallback'
};
console.log('Using local Tailwind fallback');
