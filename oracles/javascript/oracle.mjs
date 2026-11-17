// JavaScript oracle for grammar-accuracy: the TypeScript compiler's parser (pinned in
// package-lock.json) over a .js file, as a long-lived helper.
//
// Protocol: one JSON object per line on stdin, {"src": "<file text>"}; one JSON object per line
// on stdout, {"nodes": [[category, startByte, endByte], ...]} or {"rejected": "<reason>"}.
// Offsets are UTF-8 byte offsets, to match tree-sitter.
//
// A file is rejected when tsc reports any syntactic diagnostic for it as a .js file. That
// includes TypeScript-only syntax in a .js file (type annotations, `as`), which parses without
// a parse diagnostic but is not JavaScript.
import readline from 'node:readline';
import ts from 'typescript';

const K = ts.SyntaxKind;
const NAME = '/x.js';

// tsc kind -> category (the expression half of tree-sitter-typescript's scripts/tree-accuracy.mjs)
const CATS = new Map([
  [K.BinaryExpression, 'binary'],
  [K.PrefixUnaryExpression, 'unary'], [K.PostfixUnaryExpression, 'unary'],
  [K.TypeOfExpression, 'unary'], [K.VoidExpression, 'unary'], [K.DeleteExpression, 'unary'],
  [K.AwaitExpression, 'await'],
  [K.PropertyAccessExpression, 'member'],
  [K.ElementAccessExpression, 'subscript'],
  [K.CallExpression, 'call'], [K.TaggedTemplateExpression, 'call'],
  [K.NewExpression, 'new'],
  [K.ConditionalExpression, 'ternary'],
  [K.ArrowFunction, 'arrow'],
  [K.ParenthesizedExpression, 'parenthesized'],
  [K.YieldExpression, 'yield'],
  [K.SpreadElement, 'spread'], [K.SpreadAssignment, 'spread'],
]);
// JSX is built differently on the two sides
const SKIP = new Set([K.JsxElement, K.JsxSelfClosingElement, K.JsxFragment]);

function syntacticDiagnostics(sf) {
  const host = {
    getSourceFile: (f) => (f === NAME ? sf : undefined),
    fileExists: (f) => f === NAME,
    readFile: () => undefined,
    getDefaultLibFileName: () => '/lib.d.ts',
    writeFile() {},
    getCurrentDirectory: () => '/',
    getCanonicalFileName: (f) => f,
    useCaseSensitiveFileNames: () => true,
    getNewLine: () => '\n',
  };
  const program = ts.createProgram([NAME], {allowJs: true, noLib: true, noResolve: true, types: []}, host);
  return program.getSyntacticDiagnostics(sf);
}

// UTF-16 offset -> UTF-8 byte offset
function byteOffsets(text) {
  if (!/[^\x00-\x7f]/.test(text)) return null;
  const out = new Uint32Array(text.length + 1);
  let b = 0;
  for (let i = 0; i < text.length; i++) {
    out[i] = b;
    const c = text.charCodeAt(i);
    if (c < 0x80) b += 1;
    else if (c < 0x800) b += 2;
    else if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length) {
      out[i + 1] = b; // a low surrogate never starts a node
      b += 4;
      i++;
    } else b += 3;
  }
  out[text.length] = b;
  return out;
}

export function oracle(text) {
  const sf = ts.createSourceFile(NAME, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
  const diags = syntacticDiagnostics(sf);
  if (diags.length) return {rejected: ts.flattenDiagnosticMessageText(diags[0].messageText, ' ')};
  const map = byteOffsets(text);
  const at = map ? (i) => map[i] : (i) => i;
  const nodes = [];
  const visit = (n) => {
    if (SKIP.has(n.kind)) return;
    let cat = CATS.get(n.kind);
    // a comma expression is a sequence_expression in tree-sitter, nested the other way
    if (n.kind === K.BinaryExpression && n.operatorToken.kind === K.CommaToken) cat = undefined;
    if (cat) nodes.push([cat, at(n.getStart(sf)), at(n.end)]);
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return {nodes};
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const rl = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
  for await (const line of rl) {
    let reply;
    try {
      reply = oracle(JSON.parse(line).src);
    } catch (e) {
      reply = {rejected: `oracle error: ${e.message}`};
    }
    process.stdout.write(JSON.stringify(reply) + '\n');
  }
}
