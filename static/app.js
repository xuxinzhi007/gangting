const loginView = document.querySelector("#login");
const appView = document.querySelector("#app");
const loginForm = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const board = document.querySelector("#board");
const confirmBox = document.querySelector("#confirm");
const confirmText = document.querySelector("#confirm-text");
const banner = document.querySelector("#banner");
const county = document.querySelector("#county");

let pending = null;
let overviewTimer = 0;
let logTimer = 0;
let mapTimer = 0;
let mapState = null;
let picked = "";
let commandSpecs = [];
let countyReady = false;
let pickedVehicleId = null;
let vehicleTimer = 0;

function showLogin(message) {
  appView.hidden = true;
  loginView.hidden = false;
  loginError.hidden = !message;
  loginError.textContent = message || "";
  window.clearInterval(overviewTimer);
  window.clearInterval(logTimer);
  window.clearInterval(mapTimer);
}

function showApp() {
  loginView.hidden = true;
  appView.hidden = false;
  refresh();
  refreshLogs();
  refreshMap();
  loadCommands();
  window.clearInterval(overviewTimer);
  window.clearInterval(logTimer);
  window.clearInterval(mapTimer);
  overviewTimer = window.setInterval(refresh, 5000);
  logTimer = window.setInterval(refreshLogs, 10000);
  mapTimer = window.setInterval(refreshMap, 20000);
}

async function request(url, options) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && url !== "/api/login") {
    showLogin("先登录");
    throw new Error("先登录");
  }
  if (!response.ok) throw new Error(data.error || "没完成");
  return data;
}

function note(text, kind) {
  banner.hidden = !text;
  banner.textContent = text || "";
  banner.dataset.kind = text ? (kind || "info") : "";
}

function ask(text, action) {
  pending = action;
  confirmText.textContent = text;
  confirmBox.hidden = false;
}

function closeAsk() {
  pending = null;
  confirmBox.hidden = true;
}

function showReply(label, text) {
  const reply = text || "服务器没有返回文字";
  toast(label || "命令", reply, replyBad(reply) ? "error" : "");
  const local = document.querySelector("#map-reply");
  if (local) local.textContent = reply;
}

function toast(title, text, kind) {
  const stack = document.querySelector("#toasts");
  if (!stack) return;
  const item = document.createElement("article");
  item.className = kind === "error" ? "toast error" : "toast";
  const heading = document.createElement("strong");
  heading.textContent = title;
  const body = document.createElement("p");
  body.textContent = text || "";
  item.append(heading, body);
  item.addEventListener("click", () => item.remove());
  stack.append(item);
  while (stack.children.length > 4) stack.firstElementChild.remove();
  window.setTimeout(() => item.remove(), kind === "error" ? 9000 : 5600);
}

function replyBad(text) {
  return /unknown|error|fail|invalid|not found|only be|cannot|没有|无法|找不到|认不得/i.test(text || "");
}

function replaceList(id, rows, emptyText, renderRow) {
  const list = document.querySelector(id);
  list.replaceChildren();
  if (!rows.length) {
    const item = document.createElement("li");
    item.className = "empty";
    item.textContent = emptyText;
    list.append(item);
    return;
  }
  for (const row of rows) list.append(renderRow(row));
}

function renderPlayers(data) {
  const names = data.players || [];
  document.querySelector("#count").textContent = String(names.length);
  const datalist = document.querySelector("#online-names");
  datalist.replaceChildren();
  for (const name of names) {
    const option = document.createElement("option");
    option.value = name;
    datalist.append(option);
  }
  if (picked && !names.includes(picked)) picked = "";
  replaceList("#players", names, data.playerError || "现在没有人在线", (name) => {
    const item = document.createElement("li");
    item.textContent = name;
    item.classList.toggle("is-on", name === picked);
    item.addEventListener("click", () => {
      picked = name;
      renderPlayers(data);
    });
    return item;
  });
  const desk = document.querySelector("#picked");
  const actions = document.querySelector("#player-actions");
  const access = document.querySelector("#access-form");
  const ready = Boolean(picked);
  actions.hidden = !ready;
  access.hidden = !ready;
  desk.textContent = ready ? picked : "先从左边选一名在线玩家。";
}

function renderPairs(id, rows, emptyText) {
  replaceList(id, rows, emptyText, (row) => {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = row.label || row.id;
    const value = document.createElement("span");
    value.textContent = row.value || row.workshop || "没有创意工坊编号";
    item.append(label, value);
    return item;
  });
}

function formatBytes(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = number;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  const digits = size >= 10 || index === 0 ? 0 : 1;
  return `${size.toFixed(digits)} ${units[index]}`;
}

function render(data) {
  document.querySelector("#sample").hidden = !data.sample;
  document.querySelector("#server-name").textContent = data.publicName || "家用服务器";
  document.querySelector("#uptime").textContent = data.uptimeText || "没有在运行";
  document.querySelector("#state").textContent = data.stateLabel || "";
  document.querySelector("#rcon").textContent = data.rconLabel || "—";
  document.querySelector("#place").textContent = data.map || "—";
  document.querySelector("#port").textContent = data.port ? `${data.port} / ${data.udpPort || "—"}` : "—";
  document.querySelector("#max").textContent = data.maxPlayers ? `${(data.players || []).length} / ${data.maxPlayers}` : "—";
  document.querySelector("#listed").textContent = !data.public ? "关着" : (data.open ? "开着" : "开着，但要白名单");
  const usage = data.usage || {};
  document.querySelector("#cpu").textContent = usage.cpu == null ? "—" : `${usage.cpu}%`;
  document.querySelector("#mem").textContent = usage.memTotal ? `${formatBytes(usage.memUsed)} / ${formatBytes(usage.memTotal)}` : "—";
  document.querySelector("#disk").textContent = usage.diskTotal ? `${formatBytes(usage.diskUsed)} / ${formatBytes(usage.diskTotal)}` : "—";
  document.querySelector("#game-mem").textContent = usage.gameMem ? formatBytes(usage.gameMem) : "—";
  board.dataset.state = data.failed ? "failed" : (data.running ? "on" : "off");
  document.querySelector("#lamp").classList.toggle("on", Boolean(data.running) && !data.failed);
  renderPlayers(data);
  renderPairs("#mods", data.mods || [], "配置里没有启用模组");
  renderPairs("#rules", data.rules || [], "没有读到服规");
  if (data.configError) note(data.configError, "error");
  else if (data.rconError && data.running) note(data.rconError, "error");
  else if (banner.dataset.kind === "error") note("");
}

async function refresh() {
  try {
    render(await request("/api/overview"));
  } catch (error) {
    if (error.message !== "先登录") note(error.message || "面板暂时联系不上", "error");
  }
}

async function refreshLogs() {
  try {
    const data = await request("/api/logs");
    const logs = document.querySelector("#logs");
    logs.textContent = (data.lines || []).join("\n") || data.error || "日志是空的";
    logs.scrollTop = logs.scrollHeight;
    replaceList("#visits", data.visits || [], data.error || "还没有进出记录", (row) => {
      const item = document.createElement("li");
      const time = document.createElement("span");
      time.className = "when";
      time.textContent = String(row.time || "").split(" ").pop().split(".")[0];
      const body = document.createElement("span");
      body.textContent = row.name ? `${row.name} ${row.action}` : row.action;
      item.append(time, body);
      return item;
    });
    replaceList("#chat", data.chat || [], "还没有聊天", (row) => {
      const item = document.createElement("li");
      const time = document.createElement("span");
      time.className = "when";
      time.textContent = String(row.time || "").split(" ").pop().split(".")[0];
      const body = document.createElement("span");
      body.textContent = row.text;
      item.append(time, body);
      return item;
    });
  } catch (error) {
    if (error.message !== "先登录") document.querySelector("#logs").textContent = error.message;
  }
}

function showView(name) {
  for (const button of document.querySelectorAll(".nav button")) {
    button.classList.toggle("is-on", button.dataset.view === name);
  }
  for (const view of document.querySelectorAll(".view")) {
    view.hidden = view.id !== `view-${name}`;
  }
  if (name === "map") ensureCounty();
  if (name === "world") loadSandbox();
  if (name === "files") loadFiles();
  const pane = document.querySelector("#pane");
  if (pane) pane.scrollTop = 0;
}

document.querySelector(".nav").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button) showView(button.dataset.view);
});

function runCommand(id, fields, danger, label) {
  const go = () => request("/api/command", {
    method: "POST",
    body: JSON.stringify({ id, fields }),
  }).then((data) => {
    showReply(data.label || label, data.reply);
    refresh();
  });
  if (danger) ask(`执行「${label}」？`, go);
  else {
    go().catch((error) => toast("没有完成", error.message, "error"));
  }
}

function fieldControl(field) {
  if (field.kind === "select") {
    const select = document.createElement("select");
    select.name = field.name;
    for (const optionName of field.options || []) {
      const option = document.createElement("option");
      option.value = optionName;
      option.textContent = ({
        user: "普通玩家",
        priority: "优先",
        observer: "观察",
        gm: "游戏主持",
        moderator: "协管",
        admin: "管理员",
      })[optionName] || optionName;
      select.append(option);
    }
    return select;
  }
  if (field.kind === "check") {
    const wrap = document.createElement("label");
    wrap.className = "check";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = field.name;
    wrap.append(input, document.createTextNode(field.label));
    return wrap;
  }
  const input = document.createElement("input");
  input.name = field.name;
  input.type = field.kind === "password" ? "password" : field.kind === "number" ? "number" : "text";
  input.placeholder = field.placeholder || "";
  if (field.kind === "player") input.setAttribute("list", "online-names");
  if (field.min != null) input.min = String(field.min);
  if (field.max != null) input.max = String(field.max);
  return input;
}

function renderCommands(specs) {
  const boardNode = document.querySelector("#command-board");
  boardNode.replaceChildren();
  const groups = new Map();
  for (const spec of specs) {
    if (!groups.has(spec.group)) groups.set(spec.group, []);
    groups.get(spec.group).push(spec);
  }
  const root = document.createElement("div");
  root.className = "groups";
  for (const [group, items] of groups) {
    const section = document.createElement("section");
    const title = document.createElement("h2");
    title.textContent = group;
    const cards = document.createElement("div");
    cards.className = "cmd-list";
    for (const spec of items) {
      const row = document.createElement("article");
      row.className = "cmd";
      const line = document.createElement("button");
      line.type = "button";
      line.className = "cmd-line";
      const name = document.createElement("span");
      name.className = "cmd-name";
      name.textContent = spec.label;
      const official = document.createElement("code");
      official.textContent = spec.official;
      const help = document.createElement("span");
      help.className = "cmd-help";
      help.textContent = spec.help;
      line.append(name, official, help);
      const card = document.createElement("form");
      card.className = "cmd-body";
      card.hidden = true;
      for (const field of spec.fields || []) {
        const control = fieldControl(field);
        if (field.kind === "check") {
          card.append(control);
        } else {
          const label = document.createElement("label");
          label.append(document.createTextNode(field.label), control);
          card.append(label);
        }
      }
      const submit = document.createElement("button");
      submit.type = "submit";
      submit.textContent = spec.label;
      if (spec.danger) submit.className = "danger";
      card.append(submit);
      line.addEventListener("click", () => {
        const opening = card.hidden;
        for (const other of document.querySelectorAll(".cmd-body")) other.hidden = true;
        card.hidden = !opening;
      });
      card.addEventListener("submit", (event) => {
        event.preventDefault();
        const fields = {};
        for (const field of spec.fields || []) {
          const input = card.elements[field.name];
          if (field.kind === "check") fields[field.name] = input.checked;
          else fields[field.name] = input.value.trim();
          if (field.required !== false && field.kind !== "check" && !fields[field.name]) {
            toast("先填一下", `先填写${field.label}`, "error");
            return;
          }
        }
        runCommand(spec.id, fields, spec.danger, spec.label);
      });
      row.dataset.group = group;
      row.dataset.search = `${group} ${spec.label} ${spec.official} ${spec.help}`.toLowerCase();
      row.append(line, card);
      cards.append(row);
    }
    section.dataset.group = group;
    section.append(title, cards);
    root.append(section);
  }
  boardNode.append(root);
  renderCommandChips();
  applyCommandFilter();
}

let commandGroup = "";

function renderCommandChips() {
  const box = document.querySelector("#command-groups");
  box.replaceChildren();
  const names = [""];
  for (const spec of commandSpecs) {
    if (!names.includes(spec.group)) names.push(spec.group);
  }
  for (const name of names) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = commandGroup === name ? "is-on" : "quiet";
    button.textContent = name || "全部";
    button.addEventListener("click", () => {
      commandGroup = name;
      renderCommandChips();
      applyCommandFilter();
    });
    box.append(button);
  }
}

function applyCommandFilter() {
  const query = document.querySelector("#command-search").value.trim().toLowerCase();
  for (const card of document.querySelectorAll("#command-board .cmd")) {
    const groupOk = !commandGroup || card.dataset.group === commandGroup;
    const textOk = !query || (card.dataset.search || "").includes(query);
    card.hidden = !(groupOk && textOk);
  }
  for (const section of document.querySelectorAll("#command-board .groups > section")) {
    section.hidden = ![...section.querySelectorAll(".cmd")].some((card) => !card.hidden);
  }
}

document.querySelector("#command-search").addEventListener("input", applyCommandFilter);

async function loadCommands() {
  try {
    const data = await request("/api/commands");
    commandSpecs = data.commands || [];
    renderCommands(commandSpecs);
  } catch (error) {
    if (error.message !== "先登录") note(error.message, "error");
  }
}

document.querySelector("#player-actions").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button || !picked) return;
  const act = button.dataset.act;
  const plan = {
    kick: ["kickuser", { username: picked }, true],
    ban: ["banuser", { username: picked, ip: false }, true],
    "voice-off": ["voiceban", { username: picked, blocked: true }, false],
    "voice-on": ["voiceban", { username: picked, blocked: false }, false],
    "god-on": ["godmode", { username: picked, enabled: true }, false],
    "god-off": ["godmode", { username: picked, enabled: false }, false],
    "ghost-on": ["invisible", { username: picked, enabled: true }, false],
    "ghost-off": ["invisible", { username: picked, enabled: false }, false],
    "clip-on": ["noclip", { username: picked, enabled: true }, false],
    "clip-off": ["noclip", { username: picked, enabled: false }, false],
  }[act];
  if (plan) runCommand(plan[0], plan[1], plan[2], button.textContent);
});

document.querySelector("#access-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!picked) return;
  runCommand("setaccesslevel", {
    username: picked,
    level: document.querySelector("#access-level").value,
  }, true, "设置权限");
});

const TILE_CDN = "https://tiles.pzmap.org/42.20.0/base/layer0_files/";
const MAP = {
  root: "/tiles/",
  tileSize: 2048,
  maxLevel: 22,
  x0: 1040384,
  y0: -139296,
  half: 64,
  quarter: 32,
};
const MAP_PIXEL = { width: 2318656, height: 1019040 };
const view = { x: 10646, y: 9654, scale: 0.2 };
const tileCache = new Map();
let spot = null;
let mapDrag = null;

function worldToPixel(x, y) {
  return {
    x: MAP.x0 + (x - y) * MAP.half,
    y: MAP.y0 + (x + y) * MAP.quarter,
  };
}

function pixelToWorld(px, py) {
  const dx = px - MAP.x0;
  const dy = py - MAP.y0;
  return {
    x: dx / (2 * MAP.half) + dy / (2 * MAP.quarter),
    y: -dx / (2 * MAP.half) + dy / (2 * MAP.quarter),
  };
}

function screenToWorld(sx, sy, rect) {
  const center = worldToPixel(view.x, view.y);
  return pixelToWorld(
    center.x + (sx - rect.width / 2) / view.scale,
    center.y + (sy - rect.height / 2) / view.scale,
  );
}

function worldToScreen(x, y, rect) {
  const point = worldToPixel(x, y);
  const center = worldToPixel(view.x, view.y);
  return {
    sx: rect.width / 2 + (point.x - center.x) * view.scale,
    sy: rect.height / 2 + (point.y - center.y) * view.scale,
  };
}

function lookAt(x, y, z) {
  view.x = x;
  view.y = y;
  spot = { x, y, z: z || 0 };
  pickedVehicleId = null;
  const label = document.querySelector("#picked-spot");
  label.textContent = `选中 ${Math.round(x)}, ${Math.round(y)}, ${Math.round(z || 0)}`;
  drawMap();
}

function showVehicles() {
  const box = document.querySelector("#show-vehicles");
  return !box || box.checked;
}

function mapFitScale(rect) {
  const width = rect && rect.width >= 40 ? rect.width : 960;
  const height = rect && rect.height >= 40 ? rect.height : 640;
  return Math.min(width / MAP_PIXEL.width, height / MAP_PIXEL.height);
}

function tileKey(level, col, row) {
  return `${TILE_CDN}${level}/${col}_${row}.jpg`;
}

function loadTile(level, col, row, priority) {
  const direct = tileKey(level, col, row);
  const cached = tileCache.get(direct);
  if (cached) return cached;
  const image = new Image();
  image.decoding = "async";
  if (priority) image.fetchPriority = priority;
  image.onload = () => { if (!document.querySelector("#view-map").hidden) requestMapDraw(); };
  image.onerror = () => {
    if (image.dataset.fallback) return;
    image.dataset.fallback = "1";
    image.src = `${MAP.root}${level}/${col}_${row}.jpg`;
  };
  image.src = direct;
  tileCache.set(direct, image);
  return image;
}

function paintTile(ctx, rect, center, level, col, row, image) {
  const levelScale = 2 ** (MAP.maxLevel - level);
  const originX = col * MAP.tileSize * levelScale;
  const originY = row * MAP.tileSize * levelScale;
  const dw = image.naturalWidth * levelScale * view.scale + 1;
  const dh = image.naturalHeight * levelScale * view.scale + 1;
  const dx = rect.width / 2 + (originX - center.x) * view.scale;
  const dy = rect.height / 2 + (originY - center.y) * view.scale;
  ctx.drawImage(image, dx, dy, dw, dh);
}

function tileSpan(level) {
  return MAP.tileSize * 2 ** (MAP.maxLevel - level);
}

function tileBox(level, left, top, right, bottom) {
  const span = tileSpan(level);
  const maxCol = Math.max(0, Math.ceil(MAP_PIXEL.width / span) - 1);
  const maxRow = Math.max(0, Math.ceil(MAP_PIXEL.height / span) - 1);
  return {
    span,
    c0: Math.max(0, Math.min(maxCol, Math.floor(left / span))),
    c1: Math.max(0, Math.min(maxCol, Math.floor(right / span))),
    r0: Math.max(0, Math.min(maxRow, Math.floor(top / span))),
    r1: Math.max(0, Math.min(maxRow, Math.floor(bottom / span))),
  };
}

function tileCount(box) {
  if (box.c1 < box.c0 || box.r1 < box.r0) return 0;
  return (box.c1 - box.c0 + 1) * (box.r1 - box.r0 + 1);
}

function levelForScale(scale, left, top, right, bottom) {
  const safe = scale > 0 ? scale : 0.001;
  let level = Math.round(MAP.maxLevel + Math.log2(safe));
  level = Math.max(0, Math.min(MAP.maxLevel, level));
  while (level > 0 && tileCount(tileBox(level, left, top, right, bottom)) > 4) level -= 1;
  return level;
}

function requestTiles(level, box, priority) {
  for (let col = box.c0; col <= box.c1; col += 1) {
    for (let row = box.r0; row <= box.r1; row += 1) loadTile(level, col, row, priority);
  }
}

function paintReadyTiles(ctx, rect, center, level, box) {
  for (let col = box.c0; col <= box.c1; col += 1) {
    for (let row = box.r0; row <= box.r1; row += 1) {
      const image = tileCache.get(tileKey(level, col, row));
      if (image && image.complete && image.naturalWidth) paintTile(ctx, rect, center, level, col, row, image);
    }
  }
}

function prefetchOverview() {
  const center = worldToPixel(view.x, view.y);
  const span = tileSpan(11);
  loadTile(11, Math.max(0, Math.floor(center.x / span)), Math.max(0, Math.floor(center.y / span)), "high");
}
prefetchOverview();

let mapFrame = 0;

function requestMapDraw() {
  if (mapFrame) return;
  mapFrame = requestAnimationFrame(() => {
    mapFrame = 0;
    drawMap();
  });
}

function drawMap() {
  if (document.querySelector("#view-map").hidden) return;
  const rect = county.getBoundingClientRect();
  if (rect.width < 40 || rect.height < 40) return;
  const ratio = window.devicePixelRatio || 1;
  const width = Math.floor(rect.width * ratio);
  const height = Math.floor(rect.height * ratio);
  if (county.width !== width || county.height !== height) {
    county.width = width;
    county.height = height;
  }
  const ctx = county.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.fillStyle = "#111";
  ctx.fillRect(0, 0, rect.width, rect.height);
  ctx.imageSmoothingEnabled = !mapDrag;
  const center = worldToPixel(view.x, view.y);
  const left = center.x - rect.width / 2 / view.scale;
  const top = center.y - rect.height / 2 / view.scale;
  const right = center.x + rect.width / 2 / view.scale;
  const bottom = center.y + rect.height / 2 / view.scale;
  const level = levelForScale(view.scale, left, top, right, bottom);
  let cover = level;
  while (cover > 0 && tileCount(tileBox(cover, left, top, right, bottom)) > 1) cover -= 1;
  const mid = Math.max(cover, level - 3);
  const layers = [cover];
  if (mid !== cover) layers.push(mid);
  if (level !== mid) layers.push(level);
  layers.forEach((item, index) => {
    requestTiles(item, tileBox(item, left, top, right, bottom), index === layers.length - 1 ? "low" : "high");
  });
  layers.forEach((item) => paintReadyTiles(ctx, rect, center, item, tileBox(item, left, top, right, bottom)));
  ctx.font = "13px Segoe UI, Microsoft YaHei UI, sans-serif";
  if (showVehicles()) {
    for (const vehicle of (mapState && mapState.vehicles) || []) {
      if (vehicle.x == null) continue;
      const point = worldToScreen(vehicle.x, vehicle.y, rect);
      if (point.sx < -12 || point.sy < -12 || point.sx > rect.width + 12 || point.sy > rect.height + 12) continue;
      const chosen = vehicle.id === pickedVehicleId;
      ctx.fillStyle = chosen ? "#f4faf6" : "#7eb6d9";
      ctx.fillRect(point.sx - 4, point.sy - 4, 8, 8);
      if (chosen) {
        ctx.strokeStyle = "#7eb6d9";
        ctx.lineWidth = 2;
        ctx.strokeRect(point.sx - 7, point.sy - 7, 14, 14);
        ctx.fillStyle = "#f4faf6";
        ctx.fillText(String(vehicle.id), point.sx + 10, point.sy - 8);
      }
    }
  }
  for (const player of (mapState && mapState.players) || []) {
    if (player.x == null) continue;
    const point = worldToScreen(player.x, player.y, rect);
    ctx.beginPath();
    ctx.fillStyle = player.dead ? "#9d3b32" : "#e2a23a";
    ctx.arc(point.sx, point.sy, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#f4faf6";
    ctx.stroke();
    ctx.fillStyle = "#f4faf6";
    ctx.fillText(player.name, point.sx + 10, point.sy - 8);
  }
  if (spot) {
    const point = worldToScreen(spot.x, spot.y, rect);
    ctx.strokeStyle = "#f4faf6";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(point.sx - 10, point.sy);
    ctx.lineTo(point.sx + 10, point.sy);
    ctx.moveTo(point.sx, point.sy - 10);
    ctx.lineTo(point.sx, point.sy + 10);
    ctx.stroke();
  }
}

function firstPlace() {
  const placed = ((mapState && mapState.players) || []).filter((player) => player.x != null);
  if (placed.length) return placed[0];
  const town = (mapState && mapState.towns && mapState.towns[0]) || { x: 11181, y: 9725, z: 0 };
  return town;
}

function ensureCounty() {
  if (document.querySelector("#view-map").hidden || countyReady) return;
  const place = firstPlace();
  countyReady = true;
  lookAt(place.x, place.y, place.z || 0);
}

function focusPlayer(player) {
  document.querySelector("#map-player").value = player.account || player.name || "";
  if (player.x == null) {
    note("这个人还没有存档坐标", "error");
    return;
  }
  view.scale = Math.max(view.scale, 0.45);
  lookAt(player.x, player.y, player.z || 0);
  const x = Math.round(player.x);
  const y = Math.round(player.y);
  const z = Math.round(player.z || 0);
  document.querySelector("#picked-spot").textContent = `${player.name} 上次在 ${x}, ${y}, ${z}`;
}

function renderMapSwitch(data) {
  const box = document.querySelector("#map-switch");
  box.replaceChildren();
  const players = data.players || [];
  if (!players.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = data.error || "存档里还没有玩家";
    box.append(empty);
    return;
  }
  for (const player of players) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "quiet";
    const state = [player.online ? "在线" : "离线", player.dead ? "已死亡" : ""].filter(Boolean).join(" · ");
    const where = player.x == null ? "还没有坐标" : `${Math.round(player.x)}, ${Math.round(player.y)}`;
    button.textContent = `${player.name} · ${state} · ${where}`;
    button.addEventListener("click", () => focusPlayer(player));
    box.append(button);
  }
}

function renderMapPeople(data) {
  replaceList("#map-people", data.players || [], data.error || "存档里还没有坐标", (player) => {
    const item = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = [player.name, player.online ? "在线" : "", player.dead ? "已死亡" : ""].filter(Boolean).join(" · ");
    const where = document.createElement("span");
    if (player.x == null) {
      where.textContent = "还没有坐标";
    } else {
      const jump = document.createElement("button");
      jump.type = "button";
      jump.className = "quiet";
      const x = Math.round(player.x);
      const y = Math.round(player.y);
      const z = Math.round(player.z || 0);
      jump.textContent = `${x}, ${y}, ${z} · 跳到这里`;
      jump.addEventListener("click", () => focusPlayer(player));
      where.append(jump);
    }
    item.append(name, where);
    return item;
  });
}

let mapWide = false;

function mapQuery() {
  const rect = county.getBoundingClientRect();
  const width = rect.width >= 40 ? rect.width : 960;
  const height = rect.height >= 40 ? rect.height : 640;
  const box = { width, height };
  const corners = [screenToWorld(0, 0, box), screenToWorld(width, 0, box), screenToWorld(0, height, box), screenToWorld(width, height, box)];
  const xs = corners.map((point) => point.x);
  const ys = corners.map((point) => point.y);
  const pad = 40;
  const spanX = Math.max(...xs) - Math.min(...xs);
  const spanY = Math.max(...ys) - Math.min(...ys);
  mapWide = spanX > 2400 || spanY > 2400;
  const params = new URLSearchParams({
    minx: String(Math.min(...xs) - pad),
    maxx: String(Math.max(...xs) + pad),
    miny: String(Math.min(...ys) - pad),
    maxy: String(Math.max(...ys) + pad),
    vehicles: showVehicles() && !mapWide ? "1" : "0",
  });
  return `/api/map?${params}`;
}

function scheduleVehicles() {
  window.clearTimeout(vehicleTimer);
  vehicleTimer = window.setTimeout(refreshMap, 400);
}

async function refreshMap() {
  try {
    const data = await request(mapQuery());
    mapState = data;
    document.querySelector("#map-note").textContent = data.error || data.note || "";
    const count = document.querySelector("#map-vehicle-count");
    if (!showVehicles()) count.textContent = "车辆层关着";
    else if (mapWide) count.textContent = "现在是整张地图，车辆先不画。缩近到城镇后会显示。人的位置一直在图上。";
    else if (data.vehicleCapped) count.textContent = `这一带车辆很多，先画出 ${data.vehicles.length} 辆。放大后再看其余的。`;
    else count.textContent = `这一带 ${ (data.vehicles || []).length } 辆车`;
    renderMapSwitch(data);
    renderMapPeople(data);
    ensureCounty();
    if (!document.querySelector("#view-map").hidden) drawMap();
  } catch (error) {
    if (error.message !== "先登录") document.querySelector("#map-note").textContent = error.message;
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.hidden = true;
  try {
    await request("/api/login", {
      method: "POST",
      body: JSON.stringify({ password: document.querySelector("#password").value }),
    });
    showApp();
  } catch (error) {
    loginError.hidden = false;
    loginError.textContent = error.message;
  }
});

document.querySelector("#logout").addEventListener("click", async () => {
  await request("/api/logout", { method: "POST", body: "{}" });
  showLogin("");
});

function power(action, text) {
  ask(text, () => request("/api/power", {
    method: "POST",
    body: JSON.stringify({ action }),
  }).then(() => {
    note(action === "start" ? "已启动" : action === "stop" ? "已关闭" : "已重启");
    refresh();
  }));
}

document.querySelector("#start").addEventListener("click", () => power("start", "启动服务器？"));
document.querySelector("#stop").addEventListener("click", () => power("stop", "关闭服务器？会先存档，里面的人会被断开。"));
document.querySelector("#restart").addEventListener("click", () => power("restart", "重启服务器？会先存档，里面的人会被断开。"));

document.querySelector("#save").addEventListener("click", async () => {
  try {
    await request("/api/save", { method: "POST", body: "{}" });
    note("已存档");
  } catch (error) {
    note(error.message, "error");
  }
});

document.querySelector("#message-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#message");
  try {
    await request("/api/message", {
      method: "POST",
      body: JSON.stringify({ text: input.value }),
    });
    input.value = "";
    note("已发送");
  } catch (error) {
    note(error.message, "error");
  }
});

document.querySelector("#confirm-no").addEventListener("click", closeAsk);
document.querySelector("#confirm-yes").addEventListener("click", async () => {
  const action = pending;
  closeAsk();
  if (!action) return;
  try {
    await action();
  } catch (error) {
    note(error.message, "error");
  }
});

document.querySelector("#map-act").addEventListener("submit", (event) => event.preventDefault());

document.querySelector("#show-vehicles").addEventListener("change", () => {
  refreshMap();
});

document.querySelector("#map-fit").addEventListener("click", () => {
  const place = firstPlace();
  view.scale = 0.45;
  lookAt(place.x, place.y, place.z || 0);
});

document.querySelector("#map-all").addEventListener("click", () => {
  const rect = county.getBoundingClientRect();
  view.scale = mapFitScale(rect);
  const middle = pixelToWorld(MAP_PIXEL.width / 2, MAP_PIXEL.height / 2);
  view.x = middle.x;
  view.y = middle.y;
  drawMap();
  scheduleVehicles();
});

function mapPlayerName() {
  return document.querySelector("#map-player").value.trim();
}

function requireSpot() {
  if (spot) return `${Math.round(spot.x)},${Math.round(spot.y)},${Math.round(spot.z || 0)}`;
  note("先在地图上点一块地", "error");
  return "";
}

document.querySelector("#map-player").addEventListener("change", () => {
  const name = mapPlayerName();
  const player = ((mapState && mapState.players) || []).find((item) => item.account === name || item.name === name);
  if (player) focusPlayer(player);
});

document.querySelector("#map-teleport").addEventListener("click", () => {
  const username = mapPlayerName();
  const target = document.querySelector("#map-target").value.trim();
  if (!username || !target) {
    note("写上被传送的人，和另一名在线玩家。这台服务器不能把人传到点中的格子。", "error");
    return;
  }
  if (username === target) {
    note("要写成两名不同的在线玩家", "error");
    return;
  }
  runCommand("teleportplayer", { username, target }, true, "传到这名玩家身边");
});

document.querySelector("#map-vehicle").addEventListener("click", () => {
  const where = requireSpot();
  const script = document.querySelector("#map-vehicle-id").value.trim();
  if (!where || !script) return;
  runCommand("addvehicle", { script, where }, true, "在这里生成车辆");
});

document.querySelector("#map-horde").addEventListener("click", () => {
  const username = mapPlayerName();
  const count = document.querySelector("#map-horde-count").value.trim();
  if (!username) {
    note("先填写玩家。尸潮出现在这人身边", "error");
    return;
  }
  runCommand("createhorde", { username, count }, true, "在这人身边生成尸潮");
});

county.addEventListener("contextmenu", (event) => {
  event.preventDefault();
  const rect = county.getBoundingClientRect();
  const world = screenToWorld(event.clientX - rect.left, event.clientY - rect.top, rect);
  lookAt(world.x, world.y, 0);
  const menu = document.querySelector("#map-menu");
  menu.replaceChildren();
  const actions = [
    ["在这里生成车辆", "#map-vehicle"],
    ["在这人身边生成尸潮", "#map-horde"],
    ["传到这名玩家身边", "#map-teleport"],
  ];
  for (const [label, target] of actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "quiet";
    button.textContent = label;
    button.addEventListener("click", () => {
      menu.hidden = true;
      document.querySelector(target).click();
    });
    menu.append(button);
  }
  menu.hidden = false;
  menu.style.left = `${event.clientX}px`;
  menu.style.top = `${event.clientY}px`;
});
document.addEventListener("pointerdown", (event) => {
  const menu = document.querySelector("#map-menu");
  if (menu && !menu.hidden && !menu.contains(event.target)) menu.hidden = true;
});
county.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  mapDrag = { x: event.clientX, y: event.clientY, ox: view.x, oy: view.y, moved: false };
  county.setPointerCapture(event.pointerId);
});
county.addEventListener("pointermove", (event) => {
  if (!mapDrag) return;
  const dx = event.clientX - mapDrag.x;
  const dy = event.clientY - mapDrag.y;
  if (Math.hypot(dx, dy) > 4) mapDrag.moved = true;
  const center = worldToPixel(mapDrag.ox, mapDrag.oy);
  const moved = pixelToWorld(center.x - dx / view.scale, center.y - dy / view.scale);
  view.x = moved.x;
  view.y = moved.y;
  requestMapDraw();
});
function vehicleAt(sx, sy, rect) {
  if (!showVehicles()) return null;
  let best = null;
  let bestDistance = 14;
  for (const vehicle of (mapState && mapState.vehicles) || []) {
    if (vehicle.x == null) continue;
    const point = worldToScreen(vehicle.x, vehicle.y, rect);
    const distance = Math.hypot(point.sx - sx, point.sy - sy);
    if (distance < bestDistance) {
      best = vehicle;
      bestDistance = distance;
    }
  }
  return best;
}

county.addEventListener("pointerup", (event) => {
  const dragged = mapDrag && mapDrag.moved;
  mapDrag = null;
  const rect = county.getBoundingClientRect();
  if (dragged) {
    scheduleVehicles();
    return;
  }
  const localX = event.clientX - rect.left;
  const localY = event.clientY - rect.top;
  const vehicle = vehicleAt(localX, localY, rect);
  if (vehicle) {
    spot = { x: vehicle.x, y: vehicle.y, z: 0 };
    pickedVehicleId = vehicle.id;
    document.querySelector("#picked-spot").textContent = `车辆 ${vehicle.id} · ${Math.round(vehicle.x)}, ${Math.round(vehicle.y)}, 0`;
    drawMap();
    return;
  }
  const world = screenToWorld(localX, localY, rect);
  lookAt(world.x, world.y, 0);
});
county.addEventListener("wheel", (event) => {
  event.preventDefault();
  const rect = county.getBoundingClientRect();
  const before = screenToWorld(event.clientX - rect.left, event.clientY - rect.top, rect);
  const next = view.scale * (event.deltaY < 0 ? 1.15 : 0.87);
  view.scale = Math.min(16, Math.max(mapFitScale(rect), next));
  const after = screenToWorld(event.clientX - rect.left, event.clientY - rect.top, rect);
  view.x += before.x - after.x;
  view.y += before.y - after.y;
  requestMapDraw();
  scheduleVehicles();
}, { passive: false });
let sandboxFields = [];
const SANDBOX_GROUPS = {
  "": "开局",
  ZombieLore: "僵尸习性",
  ZombieConfig: "僵尸数量",
  MultiplierConfig: "倍率",
  Map: "地图",
  Basement: "地下室",
};

function sandboxGroup(name) {
  return SANDBOX_GROUPS[name] || name || "开局";
}

function renderSandbox() {
  const form = document.querySelector("#sandbox-form");
  const query = document.querySelector("#sandbox-search").value.trim().toLowerCase();
  form.replaceChildren();
  const groups = new Map();
  for (const field of sandboxFields) {
    if (field.name === "VERSION") continue;
    const haystack = [field.path, fieldZh(field.name), field.comment, translateLabel(field.comment), ...(field.options || []).map((item) => `${item.label} ${translateLabel(item.label)}`)].join(" ").toLowerCase();
    if (query && !haystack.includes(query)) continue;
    const key = field.group || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(field);
  }
  if (!groups.size) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = sandboxFields.length ? "没有匹配的沙盒项" : "还没有读到沙盒";
    form.append(empty);
    return;
  }
  for (const [key, fields] of groups) {
    const section = document.createElement("section");
    section.className = "sandbox-group";
    const title = document.createElement("h3");
    title.textContent = sandboxGroup(key);
    const grid = document.createElement("div");
    grid.className = "sandbox-fields";
    for (const field of fields) grid.append(sandboxControl(field));
    section.append(title, grid);
    form.append(section);
  }
}

function sandboxControl(field) {
  const wrap = document.createElement("label");
  const caption = document.createElement("span");
  caption.textContent = fieldZh(field.name);
  wrap.append(caption);
  const original = String(field.value);
  let input;
  if (field.kind === "bool") {
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = field.value === true;
    input.dataset.original = field.value ? "true" : "false";
  } else if (field.options && field.options.length) {
    input = document.createElement("select");
    for (const option of field.options) {
      const item = document.createElement("option");
      item.value = option.value;
      item.textContent = `${option.value} · ${translateLabel(option.label)}`;
      input.append(item);
    }
    input.value = original;
    if (input.value !== original) {
      const extra = document.createElement("option");
      extra.value = original;
      extra.textContent = original;
      input.append(extra);
      input.value = original;
    }
    input.dataset.original = original;
  } else {
    input = document.createElement("input");
    input.type = field.kind === "string" ? "text" : "number";
    if (field.kind === "float") input.step = "0.01";
    input.value = original;
    input.dataset.original = original;
  }
  input.dataset.path = field.path;
  wrap.append(input);
  if (field.comment) {
    const hint = document.createElement("span");
    hint.className = "hint";
    const translated = translateLabel(field.comment);
    const leftover = translated.replace(/[0-9.\-=,%()（）\s\u4e00-\u9fff:：]/g, "");
    hint.textContent = leftover.length > 18 ? "" : translated;
    if (hint.textContent) wrap.append(hint);
  }
  return wrap;
}

async function loadSandbox() {
  try {
    const data = await request("/api/sandbox");
    sandboxFields = data.fields || [];
    document.querySelector("#sandbox-note").textContent = data.error || data.note || "";
    renderSandbox();
  } catch (error) {
    if (error.message !== "先登录") document.querySelector("#sandbox-note").textContent = error.message;
  }
}

document.querySelector("#sandbox-search").addEventListener("input", renderSandbox);
document.querySelector("#sandbox-form").addEventListener("submit", (event) => event.preventDefault());
document.querySelector("#sandbox-save").addEventListener("click", () => {
  const values = {};
  for (const input of document.querySelectorAll("#sandbox-form [data-path]")) {
    const current = input.type === "checkbox" ? String(input.checked) : input.value;
    if (current !== input.dataset.original) values[input.dataset.path] = current;
  }
  const paths = Object.keys(values);
  if (!paths.length) {
    note("沙盒没有改动", "error");
    return;
  }
  ask(`写入 ${paths.length} 项沙盒？要重启游戏服才生效，这次不会重启。`, () => request("/api/sandbox", {
    method: "POST",
    body: JSON.stringify({ values }),
  }).then((data) => {
    note(data.changed && data.changed.length ? `已写入 ${data.changed.length} 项，重启游戏服后生效` : "沙盒没有改动");
    loadSandbox();
  }));
});

document.querySelector("#weather-rain").addEventListener("click", () => {
  runCommand("startrain", { intensity: document.querySelector("#rain-intensity").value.trim() }, true, "开始下雨");
});
document.querySelector("#weather-stop-rain").addEventListener("click", () => {
  runCommand("stoprain", {}, true, "停止下雨");
});
document.querySelector("#weather-storm").addEventListener("click", () => {
  runCommand("startstorm", { hours: document.querySelector("#storm-hours").value.trim() }, true, "开始暴风雨");
});
document.querySelector("#weather-stop").addEventListener("click", () => {
  runCommand("stopweather", {}, true, "停止天气");
});
document.querySelector("#event-chopper").addEventListener("click", () => {
  runCommand("chopper", {}, false, "直升机");
});
document.querySelector("#event-gunshot").addEventListener("click", () => {
  runCommand("gunshot", {}, false, "枪声");
});
document.querySelector("#event-lightning").addEventListener("click", () => {
  const username = document.querySelector("#event-player").value.trim();
  if (!username) {
    toast("先填一下", "闪电要写一名在线玩家", "error");
    return;
  }
  runCommand("lightning", { username }, false, "闪电");
});
document.querySelector("#event-thunder").addEventListener("click", () => {
  const username = document.querySelector("#event-player").value.trim();
  if (!username) {
    toast("先填一下", "雷声要写一名在线玩家", "error");
    return;
  }
  runCommand("thunder", { username }, false, "雷声");
});
document.querySelector("#event-zombies").addEventListener("click", () => {
  runCommand("removezombies", {}, true, "清除僵尸");
});

async function loadFiles() {
  try {
    const data = await request("/api/files");
    document.querySelector("#files-note").textContent = data.note || "";
    renderPairs("#file-mods", data.mods || [], "配置里没有启用模组");
    replaceList("#file-list", data.files || [], "没有读到文件", (row) => {
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = row.exists ? `${row.label} · ${row.kind}` : `${row.label} · 没有`;
      const value = document.createElement("span");
      value.textContent = [row.name, row.mtime].filter(Boolean).join(" · ");
      item.append(label, value);
      return item;
    });
    replaceList("#backup-list", data.backups || [], "还没有备份", (name) => {
      const item = document.createElement("li");
      item.textContent = name;
      return item;
    });
  } catch (error) {
    if (error.message !== "先登录") document.querySelector("#files-note").textContent = error.message;
  }
}

document.querySelector("#backup-now").addEventListener("click", () => {
  ask("先存档，再复制整个存档目录？不会停服，也不会恢复。", () => request("/api/backup", {
    method: "POST",
    body: "{}",
  }).then((data) => {
    toast("世界备份", data.name || "已完成");
    loadFiles();
  }).catch((error) => toast("没有完成", error.message, "error")));
});
document.querySelector("#time-apply").addEventListener("click", () => {
  runCommand("settimespeed", { period: document.querySelector("#time-speed").value.trim() }, true, "设置时间流速");
});

window.addEventListener("resize", drawMap);

request("/api/session").then((data) => {
  if (data.ok) showApp();
}).catch(() => {});
