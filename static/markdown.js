// A small Markdown view. It builds DOM nodes from text, so HTML in the source is never interpreted.
const HEADING = /^(#{1,6})\s+(.*)$/;
const LIST_ITEM = /^(\s*)([-*]|\d+\.)\s+(.*)$/;
const FENCE = /^\s*```/;
const INLINE = /`([^`]+)`|\*\*([^*]+)\*\*|\*([^*\s][^*]*)\*/g;

function parseInline(text) {
  const parts = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    if (match.index > last) parts.push({type: "text", text: text.slice(last, match.index)});
    if (match[1] !== undefined) parts.push({type: "code", text: match[1]});
    else if (match[2] !== undefined) parts.push({type: "strong", text: match[2]});
    else parts.push({type: "em", text: match[3]});
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({type: "text", text: text.slice(last)});
  return parts;
}

function parseList(lines, start) {
  const first = LIST_ITEM.exec(lines[start]);
  const root = {type: "list", ordered: /\d/.test(first[2]), items: []};
  const stack = [{indent: first[1].length, list: root}];
  let index = start;
  while (index < lines.length) {
    if (!lines[index].trim()) {
      const next = lines.slice(index).findIndex((line) => line.trim());
      if (next === -1 || !LIST_ITEM.test(lines[index + next])) break;
      index += next;
    }
    const match = LIST_ITEM.exec(lines[index]);
    if (!match) break;
    const indent = match[1].length;
    const ordered = /\d/.test(match[2]);
    while (stack.length > 1 && indent < stack[stack.length - 1].indent) stack.pop();
    let top = stack[stack.length - 1];
    if (indent > top.indent && top.list.items.length) {
      const child = {type: "list", ordered, items: []};
      top.list.items[top.list.items.length - 1].children.push(child);
      top = {indent, list: child};
      stack.push(top);
    } else if (stack.length === 1 && ordered !== root.ordered) {
      break;
    }
    top.list.items.push({inline: parseInline(match[3]), children: []});
    index += 1;
  }
  return [root, index];
}

function parseMarkdown(source) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
    } else if (FENCE.test(line)) {
      const code = [];
      index += 1;
      while (index < lines.length && !FENCE.test(lines[index])) code.push(lines[index++]);
      index += 1;
      blocks.push({type: "code", text: code.join("\n")});
    } else if (HEADING.test(line)) {
      const match = HEADING.exec(line);
      blocks.push({type: "heading", level: match[1].length, inline: parseInline(match[2].trim())});
      index += 1;
    } else if (LIST_ITEM.test(line)) {
      const [list, next] = parseList(lines, index);
      blocks.push(list);
      index = next;
    } else {
      const text = [];
      while (index < lines.length && lines[index].trim() && !HEADING.test(lines[index])
             && !LIST_ITEM.test(lines[index]) && !FENCE.test(lines[index])) {
        text.push(lines[index++].trim());
      }
      blocks.push({type: "paragraph", inline: parseInline(text.join(" "))});
    }
  }
  return blocks;
}

function appendInline(parent, parts) {
  const tags = {code: "code", strong: "strong", em: "em"};
  for (const part of parts) {
    if (part.type === "text") {
      parent.append(part.text);
    } else {
      const node = document.createElement(tags[part.type]);
      node.textContent = part.text;
      if (part.type === "code") node.dir = "ltr";
      parent.append(node);
    }
  }
}

function renderBlock(block) {
  if (block.type === "list") {
    const list = document.createElement(block.ordered ? "ol" : "ul");
    for (const item of block.items) {
      const row = document.createElement("li");
      appendInline(row, item.inline);
      for (const child of item.children) row.append(renderBlock(child));
      list.append(row);
    }
    return list;
  }
  if (block.type === "code") {
    const pre = document.createElement("pre");
    pre.dir = "auto";
    pre.textContent = block.text;
    return pre;
  }
  const node = document.createElement(block.type === "heading" ? `h${block.level}` : "p");
  appendInline(node, block.inline);
  return node;
}

function renderMarkdown(source, container) {
  container.replaceChildren(...parseMarkdown(source).map(renderBlock));
}

if (typeof module !== "undefined") module.exports = {parseMarkdown};
