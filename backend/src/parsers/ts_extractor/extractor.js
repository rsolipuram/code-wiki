/**
 * TypeScript Compiler API extractor.
 * Called from Python via subprocess; reads a .ts/.tsx/.js/.jsx file,
 * then writes JSON to stdout with entities, imports, and call edges.
 *
 * Usage: node extractor.js <file_path>
 */

"use strict";

const ts = require("typescript");
const path = require("path");
const fs = require("fs");

const filePath = process.argv[2];
const repoPath = process.argv[3];
if (!filePath) {
  process.stderr.write("Usage: node extractor.js <file_path> [repo_path]\n");
  process.exit(1);
}

const absolutePath = path.resolve(filePath);
const rootPath = repoPath ? path.resolve(repoPath) : process.cwd();
const source = fs.readFileSync(absolutePath, "utf8");

const compilerOptions = {
  target: ts.ScriptTarget.ESNext,
  module: ts.ModuleKind.CommonJS,
  strict: true,
  esModuleInterop: true,
  allowJs: true,
  jsx: ts.JsxEmit.React,
  allowSyntheticDefaultImports: true,
};

const program = ts.createProgram([absolutePath], compilerOptions);
const sourceFile = program.getSourceFile(absolutePath);
const checker = program.getTypeChecker();

if (!sourceFile) {
  process.stderr.write(`Could not parse: ${absolutePath}\n`);
  process.exit(1);
}

const entities = [];
const imports = [];
const callEdges = [];
const lines = source.split("\n");

function getLineCol(pos) {
  const lc = sourceFile.getLineAndCharacterOfPosition(pos);
  return { line: lc.line + 1, col: lc.character };
}

function getDocstring(node) {
  const ranges = ts.getLeadingCommentRanges(source, node.getFullStart());
  if (!ranges || ranges.length === 0) return null;
  const last = ranges[ranges.length - 1];
  const text = source.slice(last.pos, last.end);
  if (text.startsWith("/**")) {
    // Strip /** ... */ wrapper and leading * on each line
    return text
      .replace(/^\/\*\*/, "")
      .replace(/\*\/$/, "")
      .split("\n")
      .map((l) => l.replace(/^\s*\*\s?/, ""))
      .join("\n")
      .trim();
  }
  return null;
}

function getTypeStr(node) {
  try {
    const type = checker.getTypeAtLocation(node);
    return checker.typeToString(type);
  } catch {
    return null;
  }
}

function buildSignature(node) {
  // Use printer to produce a clean signature string
  const printer = ts.createPrinter({ removeComments: true });
  try {
    // Print just the declaration without the body
    if (ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node) || ts.isArrowFunction(node)) {
      const params = node.parameters
        .map((p) => {
          const name = p.name.getText(sourceFile);
          const typeStr = p.type ? p.type.getText(sourceFile) : null;
          const opt = p.questionToken ? "?" : "";
          const def = p.initializer ? ` = ${p.initializer.getText(sourceFile)}` : "";
          return typeStr ? `${name}${opt}: ${typeStr}${def}` : `${name}${opt}${def}`;
        })
        .join(", ");
      const ret = node.type ? `: ${node.type.getText(sourceFile)}` : "";
      const name =
        ts.isFunctionDeclaration(node) && node.name
          ? node.name.getText(sourceFile)
          : ts.isMethodDeclaration(node) && node.name
          ? node.name.getText(sourceFile)
          : "(anonymous)";
      const async = node.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword) ? "async " : "";
      return `${async}function ${name}(${params})${ret}`;
    }
  } catch {
    // fall through
  }
  return null;
}

function extractCalls(node, callerName) {
  ts.forEachChild(node, function walk(child) {
    if (ts.isCallExpression(child)) {
      let callee = "";
      if (ts.isIdentifier(child.expression)) {
        callee = child.expression.text;
      } else if (ts.isPropertyAccessExpression(child.expression)) {
        callee = child.expression.getText(sourceFile);
      }
      if (callee) {
        callEdges.push({ caller: callerName, callee });
      }
    }
    ts.forEachChild(child, walk);
  });
}

const moduleName = path
  .relative(rootPath, absolutePath)
  .replace(/\\/g, "/")
  .replace(/\.(ts|tsx|js|jsx)$/, "")
  .replace(/\//g, ".");

function visitNode(node, parentClass) {
  // Import declarations
  if (ts.isImportDeclaration(node)) {
    const moduleSpec = node.moduleSpecifier.getText(sourceFile).replace(/['"]/g, "");
    const clause = node.importClause;
    if (clause) {
      if (clause.name) {
        imports.push({ imported_name: moduleSpec + ".default", source_file: absolutePath });
      }
      if (clause.namedBindings) {
        if (ts.isNamedImports(clause.namedBindings)) {
          clause.namedBindings.elements.forEach((el) => {
            imports.push({
              imported_name: `${moduleSpec}.${el.name.text}`,
              source_file: absolutePath,
            });
          });
        } else if (ts.isNamespaceImport(clause.namedBindings)) {
          imports.push({ imported_name: moduleSpec, source_file: absolutePath });
        }
      }
    } else {
      imports.push({ imported_name: moduleSpec, source_file: absolutePath });
    }
  }

  // Class declarations
  if (ts.isClassDeclaration(node) && node.name) {
    const className = node.name.text;
    const qname = `${moduleName}.${className}`;
    const startLine = getLineCol(node.getStart(sourceFile)).line;
    const endLine = getLineCol(node.getEnd()).line;
    const bases = [];
    if (node.heritageClauses) {
      node.heritageClauses.forEach((hc) => {
        hc.types.forEach((t) => bases.push(t.expression.getText(sourceFile)));
      });
    }
    entities.push({
      name: className,
      qualified_name: qname,
      entity_type: "class",
      file_path: absolutePath,
      line_start: startLine,
      line_end: endLine,
      docstring: getDocstring(node),
      entity_metadata: { bases, is_exported: !!(ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Export) },
    });

    // Visit class members
    node.members.forEach((member) => {
      if (ts.isMethodDeclaration(member) && member.name) {
        const methodName = member.name.getText(sourceFile);
        const mQname = `${qname}.${methodName}`;
        const mStart = getLineCol(member.getStart(sourceFile)).line;
        const mEnd = getLineCol(member.getEnd()).line;
        extractCalls(member, mQname);
        entities.push({
          name: methodName,
          qualified_name: mQname,
          entity_type: "method",
          file_path: absolutePath,
          line_start: mStart,
          line_end: mEnd,
          signature: buildSignature(member),
          docstring: getDocstring(member),
          entity_metadata: {
            class: className,
            is_static: !!(ts.getCombinedModifierFlags(member) & ts.ModifierFlags.Static),
            is_async: !!(ts.getCombinedModifierFlags(member) & ts.ModifierFlags.Async),
            is_exported: !!(ts.getCombinedModifierFlags(member) & ts.ModifierFlags.Export),
          },
        });
      } else if (ts.isPropertyDeclaration(member) && member.name) {
        const propName = member.name.getText(sourceFile);
        const pStart = getLineCol(member.getStart(sourceFile)).line;
        entities.push({
          name: propName,
          qualified_name: `${qname}.${propName}`,
          entity_type: "variable",
          file_path: absolutePath,
          line_start: pStart,
          line_end: pStart,
          entity_metadata: { class: className, type: member.type ? member.type.getText(sourceFile) : null },
        });
      }
    });
  }

  // Function declarations
  if (ts.isFunctionDeclaration(node) && node.name && !parentClass) {
    const fnName = node.name.text;
    const qname = `${moduleName}.${fnName}`;
    const startLine = getLineCol(node.getStart(sourceFile)).line;
    const endLine = getLineCol(node.getEnd()).line;
    extractCalls(node, qname);
    entities.push({
      name: fnName,
      qualified_name: qname,
      entity_type: "function",
      file_path: absolutePath,
      line_start: startLine,
      line_end: endLine,
      signature: buildSignature(node),
      docstring: getDocstring(node),
      entity_metadata: {
        is_async: !!(ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Async),
        is_exported: !!(ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Export),
      },
    });
  }

  // Variable statements (const foo = () => ...)
  if (ts.isVariableStatement(node) && !parentClass) {
    node.declarationList.declarations.forEach((decl) => {
      if (ts.isIdentifier(decl.name) && decl.initializer) {
        const varName = decl.name.text;
        const qname = `${moduleName}.${varName}`;
        const startLine = getLineCol(decl.getStart(sourceFile)).line;

        if (ts.isArrowFunction(decl.initializer) || ts.isFunctionExpression(decl.initializer)) {
          extractCalls(decl.initializer, qname);
          entities.push({
            name: varName,
            qualified_name: qname,
            entity_type: "function",
            file_path: absolutePath,
            line_start: startLine,
            line_end: getLineCol(decl.getEnd()).line,
            docstring: getDocstring(node),
            entity_metadata: {
              is_arrow: ts.isArrowFunction(decl.initializer),
              is_exported: !!(ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Export),
            },
          });
        } else {
          entities.push({
            name: varName,
            qualified_name: qname,
            entity_type: "variable",
            file_path: absolutePath,
            line_start: startLine,
            line_end: startLine,
            entity_metadata: {
              type: getTypeStr(decl),
              is_exported: !!(ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Export),
            },
          });
        }
      }
    });
  }

  // Interface declarations
  if (ts.isInterfaceDeclaration(node)) {
    const ifName = node.name.text;
    const qname = `${moduleName}.${ifName}`;
    const startLine = getLineCol(node.getStart(sourceFile)).line;
    entities.push({
      name: ifName,
      qualified_name: qname,
      entity_type: "class",  // treat interface as class-like
      file_path: absolutePath,
      line_start: startLine,
      line_end: getLineCol(node.getEnd()).line,
      docstring: getDocstring(node),
      entity_metadata: {
        is_interface: true,
        is_exported: !!(ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Export),
      },
    });
  }

  ts.forEachChild(node, (child) => visitNode(child, null));
}

ts.forEachChild(sourceFile, (node) => visitNode(node, null));

// Add module-level entity
entities.unshift({
  name: path.basename(absolutePath, path.extname(absolutePath)),
  qualified_name: moduleName,
  entity_type: "module",
  file_path: absolutePath,
  line_start: 1,
  line_end: lines.length,
  entity_metadata: {},
});

process.stdout.write(JSON.stringify({ entities, imports, call_edges: callEdges }, null, 0));
