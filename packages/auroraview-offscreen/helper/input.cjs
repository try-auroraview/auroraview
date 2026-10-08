'use strict';

const keyCodes = { Backspace: 8, Tab: 9, Enter: 13, Shift: 16, Control: 17,
  Alt: 18, Pause: 19, CapsLock: 20, Escape: 27, ' ': 32, PageUp: 33,
  PageDown: 34, End: 35, Home: 36, ArrowLeft: 37, ArrowUp: 38,
  ArrowRight: 39, ArrowDown: 40, Insert: 45, Delete: 46, Meta: 91,
  ContextMenu: 93, NumLock: 144, ScrollLock: 145 };
const physicalCodes = { Space: 32, MetaLeft: 91, MetaRight: 92,
  Semicolon: 186, Equal: 187, Comma: 188, Minus: 189, Period: 190,
  Slash: 191, Backquote: 192, BracketLeft: 219, Backslash: 220,
  BracketRight: 221, Quote: 222, NumpadMultiply: 106, NumpadAdd: 107,
  NumpadSubtract: 109, NumpadDecimal: 110, NumpadDivide: 111,
  NumpadEnter: 13 };

function keyEvent(event) {
  const code = event.code || '';
  let virtualKey = physicalCodes[code];
  if (/^Key[A-Z]$/.test(code)) virtualKey = code.charCodeAt(3);
  else if (/^Digit[0-9]$/.test(code)) virtualKey = code.charCodeAt(5);
  else if (/^Numpad[0-9]$/.test(code)) virtualKey = 96 + Number(code[6]);
  else if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) virtualKey = 111 + Number(code.slice(1));
  if (virtualKey === undefined) virtualKey = keyCodes[event.key] ||
    (/^[a-z0-9]$/i.test(event.key) ? event.key.toUpperCase().charCodeAt(0) : 0);
  const location = code.startsWith('Numpad') ? 3 : /^(Shift|Control|Alt|Meta)Right$/.test(code) ? 2 :
    /^(Shift|Control|Alt|Meta)Left$/.test(code) ? 1 : 0;
  return { type: event.type === 'keyUp' ? 'keyUp' : 'rawKeyDown',
    key: event.key, code, windowsVirtualKeyCode: virtualKey,
    modifiers: event.modifiers || 0, location, isKeypad: location === 3 };
}

module.exports = { keyEvent };
