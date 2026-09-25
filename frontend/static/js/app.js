/* =====================================================================
   Rider Live Map — logic ฝั่งเบราว์เซอร์

   การทำงาน:
     กด "ดึงออเดอร์จาก text.csv" -> Django ขอ 1 แถวจากชุดทดสอบจริง (มีเฉลย)
     -> Backend ทำนายด้วย 2 โมเดล แล้วเทียบกับเฉลย -> หน้าเว็บแสดงผลเปรียบเทียบ
     -> ไรเดอร์วิ่งบนแผนที่ตาม "เวลาจริง" (เฉลย) ไม่ใช่ตามคำทำนาย

   กด "ทดสอบทั้ง 1,000 แถว" -> Backend ประเมินทั้งชุด แล้วสรุป MAE / %Accuracy / Win rate

   ทุก request ยิงไปที่ Django (/api/...) ไม่ได้ยิงตรงไปหา FastAPI
   (Django ทำหน้าที่ proxy จึงไม่ต้องยุ่งกับ CORS และ URL ของ Backend ไม่หลุดมาฝั่ง client)

   โครงไฟล์:
     1. ตัวช่วยทั่วไป
     2. ระบบพิกัด: lat/lon -> พิกัดบน SVG
     3. วาดแผนที่เมือง (seeded — เมืองเดิมได้ลวดลายเดิม)
     4. เส้นทางและหมุด
     5. วงจรชีวิตของไรเดอร์ (สร้าง / เดินทาง / ส่งถึง)
     6. แถบข้างและการ์ด ETA
     7. Modal รายละเอียด
     8. สถานะ Backend
   ===================================================================== */
(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";

  // ===================================================================
  // 1) ตัวช่วยทั่วไป
  // ===================================================================
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  function readJSON(id, fallback) {
    const el = document.getElementById(id);
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent);
    } catch (err) {
      console.error("อ่าน JSON จาก #" + id + " ไม่สำเร็จ", err);
      return fallback;
    }
  }

  const CITIES = readJSON("city-data", []);
  const CITY_BY_CODE = {};
  CITIES.forEach((c) => (CITY_BY_CODE[c.code] = c));

  const TESTSET = readJSON("testset-info", {});
  const TESTSET_TOTAL = Number(TESTSET.count) || 1000;

  function csrfTokenFromCookie() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  async function apiFetch(url, options = {}) {
    const opts = Object.assign({ headers: {} }, options);
    opts.headers = Object.assign(
      { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      opts.headers
    );
    if ((opts.method || "GET").toUpperCase() !== "GET") {
      opts.headers["X-CSRFToken"] = csrfTokenFromCookie();
    }

    let response;
    try {
      response = await fetch(url, opts);
    } catch (err) {
      throw new Error("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจสอบการเชื่อมต่ออินเทอร์เน็ต");
    }

    let data = null;
    try {
      data = await response.json();
    } catch (err) {
      throw new Error("เซิร์ฟเวอร์ตอบกลับในรูปแบบที่ไม่คาดคิด (HTTP " + response.status + ")");
    }
    if (!response.ok) {
      throw new Error(data && data.error ? data.error : "เกิดข้อผิดพลาด (HTTP " + response.status + ")");
    }
    return data;
  }

  const fmt = (n, d = 1) =>
    Number(n).toLocaleString("th-TH", { minimumFractionDigits: d, maximumFractionDigits: d });

  const show = (el, visible) => { if (el) el.hidden = !visible; };

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function svgEl(tag, attrs) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const key in attrs) el.setAttribute(key, attrs[key]);
    return el;
  }

  /** PRNG แบบ seed ได้ (mulberry32) — เมืองเดิมจะได้ลวดลายแผนที่เดิมเสมอ */
  function seededRandom(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function hashString(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  // ===================================================================
  // 2) ระบบพิกัด
  // ===================================================================
  // ขนาด viewBox ถูกตั้งให้เท่ากับขนาดจริงของกล่องแผนที่ (หน่วย SVG = พิกเซล CSS)
  // เพื่อให้คำนวณ "พื้นที่ปลอดภัย" ได้แม่น และไม่มีส่วนไหนของ viewBox ถูก slice ตัดทิ้ง
  let MAP_W = 1000;
  let MAP_H = 720;
  const PAD = 0.22; // เผื่อขอบรอบเส้นทาง 22%

  // กรอบพิกัดที่กำลังแสดงอยู่ (ตั้งใหม่ทุกครั้งที่โฟกัสไรเดอร์คนใหม่)
  let viewport = null;

  /** ปรับ viewBox ให้ตรงกับขนาดกล่องแผนที่จริง */
  function syncMapSize() {
    const box = $(".mapwrap").getBoundingClientRect();
    MAP_W = Math.max(320, Math.round(box.width));
    MAP_H = Math.max(280, Math.round(box.height));
    const svg = $("#map");
    svg.setAttribute("viewBox", "0 0 " + MAP_W + " " + MAP_H);
    const bg = svg.querySelector(".map__bg");
    bg.setAttribute("width", MAP_W);
    bg.setAttribute("height", MAP_H);
  }

  /**
   * พื้นที่ปลอดภัย: บริเวณที่ไม่มีแผงลอย (การ์ด ETA / ป้ายเมือง / แผงควบคุม) บังอยู่
   * วัดจากตำแหน่งจริงของ element เพื่อให้ปรับตามขนาดจอเองโดยไม่ต้องฮาร์ดโค้ด
   */
  function safeInsets() {
    const map = $(".mapwrap").getBoundingClientRect();
    const inset = { top: 28, right: 28, bottom: 28, left: 28 };

    const consider = (el, side) => {
      if (!el || el.hidden) return;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      // สนใจเฉพาะ element ที่ลอยทับแผนที่จริง ๆ (มือถือจะวางแบบ static จึงไม่ทับ)
      if (r.bottom < map.top || r.top > map.bottom) return;
      if (side === "right") inset.right = Math.max(inset.right, map.right - r.left + 16);
      if (side === "bottom") inset.bottom = Math.max(inset.bottom, map.bottom - r.top + 16);
      if (side === "top") inset.top = Math.max(inset.top, r.bottom - map.top + 16);
    };

    consider($("#eta-card"), "right");
    consider($(".controls"), "bottom");
    consider($("#map-city"), "top");

    // จอเล็กมาก: อย่าให้ขอบกินจนไม่เหลือพื้นที่วาด
    const maxX = MAP_W * 0.34;
    const maxY = MAP_H * 0.30;
    inset.left = Math.min(inset.left, maxX);
    inset.right = Math.min(inset.right, maxX);
    inset.top = Math.min(inset.top, maxY);
    inset.bottom = Math.min(inset.bottom, maxY);
    return inset;
  }

  /** คำนวณกรอบพิกัดให้ครอบคลุมร้าน+จุดส่ง โดยคงอัตราส่วนของแผนที่ไว้ */
  function makeViewport(latA, lonA, latB, lonB) {
    let latMin = Math.min(latA, latB);
    let latMax = Math.max(latA, latB);
    let lonMin = Math.min(lonA, lonB);
    let lonMax = Math.max(lonA, lonB);

    const padLat = Math.max((latMax - latMin) * PAD, 0.012);
    const padLon = Math.max((lonMax - lonMin) * PAD, 0.012);
    latMin -= padLat; latMax += padLat;
    lonMin -= padLon; lonMax += padLon;

    // ปรับให้อัตราส่วนกรอบพิกัดตรงกับอัตราส่วนของพื้นที่ปลอดภัย ไม่งั้นเส้นทางจะดูบิด
    const inset = safeInsets();
    const aspect = (MAP_W - inset.left - inset.right) / (MAP_H - inset.top - inset.bottom);
    const spanLat = latMax - latMin;
    const spanLon = lonMax - lonMin;
    if (spanLon / spanLat < aspect) {
      const want = spanLat * aspect;
      const mid = (lonMin + lonMax) / 2;
      lonMin = mid - want / 2;
      lonMax = mid + want / 2;
    } else {
      const want = spanLon / aspect;
      const mid = (latMin + latMax) / 2;
      latMin = mid - want / 2;
      latMax = mid + want / 2;
    }
    return { latMin, latMax, lonMin, lonMax };
  }

  /** lat/lon -> {x, y} บน SVG โดยวางลงเฉพาะพื้นที่ปลอดภัย (lat มากอยู่ด้านบน จึงกลับแกน y) */
  function project(lat, lon) {
    if (!viewport) return { x: MAP_W / 2, y: MAP_H / 2 };
    const inset = safeInsets();
    const w = MAP_W - inset.left - inset.right;
    const h = MAP_H - inset.top - inset.bottom;
    const fx = (lon - viewport.lonMin) / (viewport.lonMax - viewport.lonMin);
    const fy = (lat - viewport.latMin) / (viewport.latMax - viewport.latMin);
    return { x: inset.left + fx * w, y: inset.top + (1 - fy) * h };
  }

  // ===================================================================
  // 3) วาดแผนที่เมือง
  // ===================================================================
  /**
   * วาดพื้นหลังเมือง: แม่น้ำ / สวน / บล็อกอาคาร / ถนน
   * ทุกอย่างสุ่มด้วย seed จากรหัสเมือง -> เมืองเดิมได้หน้าตาเดิมทุกครั้ง
   */
  function drawCity(cityCode) {
    const terrain = $("#layer-terrain");
    const blocks = $("#layer-blocks");
    const roads = $("#layer-roads");
    [terrain, blocks, roads].forEach((g) => (g.innerHTML = ""));

    const rand = seededRandom(hashString(cityCode || "DEFAULT"));

    // --- แม่น้ำ: เส้นโค้งหนาพาดผ่านแผนที่ ---
    const riverY = 140 + rand() * 440;
    const bend = 90 + rand() * 150;
    terrain.appendChild(
      svgEl("path", {
        class: "mp-water",
        d:
          "M -40 " + riverY +
          " C 260 " + (riverY - bend) +
          ", 620 " + (riverY + bend) +
          ", 1040 " + (riverY - bend * 0.4) +
          " L 1040 " + (riverY - bend * 0.4 + 46) +
          " C 620 " + (riverY + bend + 46) +
          ", 260 " + (riverY - bend + 46) +
          ", -40 " + (riverY + 46) + " Z",
      })
    );

    // --- สวนสาธารณะ 2-3 แห่ง ---
    const parkCount = 2 + Math.floor(rand() * 2);
    for (let i = 0; i < parkCount; i++) {
      terrain.appendChild(
        svgEl("rect", {
          class: "mp-park",
          x: rand() * 840,
          y: rand() * 580,
          width: 90 + rand() * 130,
          height: 70 + rand() * 110,
          rx: 18,
        })
      );
    }

    // --- บล็อกอาคาร: ตารางเมืองแบบมีช่องว่างบ้าง ---
    const cell = 76;
    for (let gx = 0; gx < MAP_W / cell + 1; gx++) {
      for (let gy = 0; gy < MAP_H / cell + 1; gy++) {
        if (rand() < 0.30) continue; // เว้นเป็นลานโล่ง
        const inset = 7 + rand() * 12;
        blocks.appendChild(
          svgEl("rect", {
            class: rand() < 0.35 ? "mp-block mp-block--alt" : "mp-block",
            x: gx * cell + inset,
            y: gy * cell + inset,
            width: cell - inset * 2 - rand() * 12,
            height: cell - inset * 2 - rand() * 12,
            rx: 3,
          })
        );
      }
    }

    // --- ถนนซอย: ตารางบาง ๆ ---
    for (let gx = 0; gx <= MAP_W / cell; gx++) {
      roads.appendChild(
        svgEl("line", { class: "mp-road", x1: gx * cell, y1: 0, x2: gx * cell, y2: MAP_H, "stroke-width": 5 })
      );
    }
    for (let gy = 0; gy <= MAP_H / cell; gy++) {
      roads.appendChild(
        svgEl("line", { class: "mp-road", x1: 0, y1: gy * cell, x2: MAP_W, y2: gy * cell, "stroke-width": 5 })
      );
    }

    // --- ถนนสายหลัก: หนากว่า สว่างกว่า อย่างละ 2 เส้น ---
    const mainX = Math.floor(rand() * (MAP_W / cell)) * cell;
    const mainY = Math.floor(rand() * (MAP_H / cell)) * cell;
    roads.appendChild(
      svgEl("line", { class: "mp-road mp-road--main", x1: mainX, y1: 0, x2: mainX, y2: MAP_H, "stroke-width": 13 })
    );
    roads.appendChild(
      svgEl("line", { class: "mp-road mp-road--main", x1: 0, y1: mainY, x2: MAP_W, y2: mainY, "stroke-width": 13 })
    );
  }

  // ===================================================================
  // 4) เส้นทาง
  // ===================================================================
  /**
   * สร้างเส้นทางแบบ "วิ่งตามถนน" — หักมุมเป็นขั้นบันไดแทนเส้นตรง
   * ให้ดูสมจริงกว่าการลากเส้นตรงทะลุตึก
   */
  function buildRoutePath(from, to, seed) {
    const rand = seededRandom(seed);
    const dx = to.x - from.x;
    const dy = to.y - from.y;

    // แบ่งเป็น 3 ช่วง สลับเดินแนวนอน/แนวตั้ง พร้อมสุ่มจุดหักเล็กน้อย
    const k1 = 0.35 + rand() * 0.2;
    const k2 = 0.62 + rand() * 0.2;
    const horizontalFirst = Math.abs(dx) > Math.abs(dy) ? rand() < 0.7 : rand() < 0.3;

    const p = [from];
    if (horizontalFirst) {
      p.push({ x: from.x + dx * k1, y: from.y });
      p.push({ x: from.x + dx * k1, y: from.y + dy * k2 });
      p.push({ x: from.x + dx * k2, y: from.y + dy * k2 });
      p.push({ x: from.x + dx * k2, y: to.y });
    } else {
      p.push({ x: from.x, y: from.y + dy * k1 });
      p.push({ x: from.x + dx * k2, y: from.y + dy * k1 });
      p.push({ x: from.x + dx * k2, y: from.y + dy * k2 });
      p.push({ x: to.x, y: from.y + dy * k2 });
    }
    p.push(to);

    // ลบมุมให้มนด้วย quadratic corner (ดูเหมือนเลี้ยวรถจริง)
    const R = 16;
    let d = "M " + p[0].x.toFixed(1) + " " + p[0].y.toFixed(1);
    for (let i = 1; i < p.length - 1; i++) {
      const prev = p[i - 1], cur = p[i], next = p[i + 1];
      const inLen = Math.hypot(cur.x - prev.x, cur.y - prev.y) || 1;
      const outLen = Math.hypot(next.x - cur.x, next.y - cur.y) || 1;
      const r1 = Math.min(R, inLen / 2);
      const r2 = Math.min(R, outLen / 2);
      const a = { x: cur.x - ((cur.x - prev.x) / inLen) * r1, y: cur.y - ((cur.y - prev.y) / inLen) * r1 };
      const b = { x: cur.x + ((next.x - cur.x) / outLen) * r2, y: cur.y + ((next.y - cur.y) / outLen) * r2 };
      d += " L " + a.x.toFixed(1) + " " + a.y.toFixed(1);
      d += " Q " + cur.x.toFixed(1) + " " + cur.y.toFixed(1) + " " + b.x.toFixed(1) + " " + b.y.toFixed(1);
    }
    const last = p[p.length - 1];
    d += " L " + last.x.toFixed(1) + " " + last.y.toFixed(1);
    return d;
  }

  // ===================================================================
  // 5) วงจรชีวิตของไรเดอร์
  // ===================================================================
  const MAX_RIDERS = 8;
  const MS_PER_MINUTE = 900; // 1 นาทีจริง = 0.9 วินาทีบนหน้าจอ (ที่ความเร็ว 1×)
  const MAX_HISTORY = 12;    // เก็บประวัติผลเปรียบเทียบไว้กี่รายการ

  const VEHICLE_ICON = { motorcycle: "🏍️", scooter: "🛵", electric_scooter: "⚡", bicycle: "🚲" };
  const PERIOD_TH = {
    Morning: "เช้า (05–11)", Afternoon: "กลางวัน (11–15)",
    Evening: "เย็น (15–20)", Night: "กลางคืน (20–05)",
  };
  const DAY_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"];

  /** riders: { id, order, cityName, cityCode, prediction, progress, done, els } */
  const riders = [];
  const history = [];   // ผลเปรียบเทียบย้อนหลัง (ไว้นับสกอร์รวม)
  let selectedId = null;
  let nextId = 1;
  let speed = 1;
  let rafHandle = null;

  function etaColor(minutes) {
    if (minutes <= 20) return "#34d399";
    if (minutes <= 30) return "#ffc93d";
    if (minutes <= 40) return "#ff8a3d";
    return "#f87171";
  }

  const btnGenerate = $("#btn-generate");

  btnGenerate.addEventListener("click", async () => {
    btnGenerate.disabled = true;
    const original = btnGenerate.innerHTML;
    btnGenerate.innerHTML = "<span>⏳</span> กำลังดึง…";
    show($("#map-error"), false);

    try {
      // /api/test-sample/ ดึงแถวจาก text.csv + ให้ 2 โมเดลทำนาย + เทียบเฉลย ในครั้งเดียว
      const raw = $("#sample-index").value.trim();
      const query = raw === "" ? "" : "?index=" + encodeURIComponent(raw);
      const data = await apiFetch("/api/test-sample/" + query);
      addRider(data);
      setBackendStatus(true, "โมเดลพร้อม");
    } catch (err) {
      const box = $("#map-error");
      box.textContent = err.message;
      show(box, true);
      setBackendStatus(false, "โมเดลมีปัญหา");
    } finally {
      btnGenerate.disabled = false;
      btnGenerate.innerHTML = original;
    }
  });

  /**
   * รับผลจาก /compare/test-sample แล้วเพิ่มออเดอร์ลงแผนที่
   *
   * รูปแบบที่ได้: { test_index, order, actual_minutes, tuned, baseline, comparison,
   *                derived_features, warnings }
   * ไรเดอร์วิ่งตาม actual_minutes (เวลาจริง) เพราะนั่นคือสิ่งที่เกิดขึ้นจริง
   * ส่วนคำทำนายของสองโมเดลเอาไว้เทียบว่าใครใกล้เคียงกว่ากัน
   */
  function addRider(result) {
    // เกินจำนวนสูงสุด -> เอาคนที่ส่งเสร็จแล้วออกก่อน ถ้าไม่มีค่อยเอาคนเก่าสุด
    if (riders.length >= MAX_RIDERS) {
      const idx = riders.findIndex((r) => r.done);
      removeRider(riders[idx >= 0 ? idx : 0].id);
    }

    const order = result.order;
    const cityCode = (order.Delivery_person_ID || "XXXX").slice(0, 4);
    const city = CITY_BY_CODE[cityCode];

    const rider = {
      id: nextId++,
      testIndex: result.test_index,
      order: order,
      cityCode: cityCode,
      cityName: city ? city.name : cityCode,
      result: result,
      actual: Number(result.actual_minutes),
      // แผนที่เดินตามเวลาจริง ไม่ใช่คำทำนาย
      minutes: Number(result.actual_minutes),
      progress: 0,
      done: false,
      els: {},
    };
    riders.push(rider);

    buildRiderSvg(rider);
    selectRider(rider.id);
    pushHistory(rider);

    show($("#map-empty"), false);
    refreshSidebar();
    startLoop();
  }

  /** สร้างเส้นทาง + หมุด + ตัวไรเดอร์ลงบน SVG */
  function buildRiderSvg(rider) {
    const o = rider.order;
    // คำนวณตำแหน่งด้วย viewport ปัจจุบัน — จะคำนวณใหม่ทุกครั้งที่โฟกัสเปลี่ยน
    const routeGroup = svgEl("g", { class: "route", "data-rider": rider.id });
    const base = svgEl("path", { class: "route__base" });
    const done = svgEl("path", { class: "route__done" });
    routeGroup.append(base, done);
    $("#layer-routes").appendChild(routeGroup);

    const markerGroup = svgEl("g", { class: "marker", "data-rider": rider.id });

    // หมุดร้านอาหาร
    const shop = svgEl("g", { class: "pin" });
    shop.append(
      svgEl("circle", { class: "pin__halo", r: 19 }),
      svgEl("circle", { class: "pin__body", r: 13 })
    );
    const shopIcon = svgEl("text", { class: "pin__icon" });
    shopIcon.textContent = "🍜";
    const shopLabel = svgEl("text", { class: "pin__label" });
    shopLabel.textContent = "ร้านอาหาร";
    shop.append(shopIcon, shopLabel);

    // หมุดจุดส่ง
    const home = svgEl("g", { class: "pin pin--dest" });
    home.append(
      svgEl("circle", { class: "pin__halo", r: 19 }),
      svgEl("circle", { class: "pin__body", r: 13 })
    );
    const homeIcon = svgEl("text", { class: "pin__icon" });
    homeIcon.textContent = "🏠";
    const homeLabel = svgEl("text", { class: "pin__label" });
    homeLabel.textContent = "จุดส่ง";
    home.append(homeIcon, homeLabel);

    // ตัวไรเดอร์
    const rider_g = svgEl("g", { class: "rider" });
    rider_g.append(
      svgEl("circle", { class: "rider__glow", r: 26 }),
      svgEl("circle", { class: "rider__ping", r: 12 }),
      svgEl("circle", { class: "rider__disc", r: 13 })
    );
    const riderIcon = svgEl("text", { class: "rider__icon" });
    riderIcon.textContent = VEHICLE_ICON[o.Type_of_vehicle] || "🛵";
    rider_g.appendChild(riderIcon);

    markerGroup.append(shop, home, rider_g);
    $("#layer-markers").appendChild(markerGroup);

    rider.els = {
      routeGroup, base, done, markerGroup,
      shop, shopIcon, shopLabel,
      home, homeIcon, homeLabel,
      riderG: rider_g, riderIcon,
    };
  }

  /** วางตำแหน่งทุกอย่างใหม่ตาม viewport ปัจจุบัน (เรียกเมื่อโฟกัสเปลี่ยน) */
  function layoutRider(rider) {
    const o = rider.order;
    const from = project(o.Restaurant_latitude, o.Restaurant_longitude);
    const to = project(o.Delivery_location_latitude, o.Delivery_location_longitude);
    const e = rider.els;

    const d = buildRoutePath(from, to, hashString(o.ID || String(rider.id)));
    e.base.setAttribute("d", d);
    e.done.setAttribute("d", d);
    rider.pathLength = e.done.getTotalLength();

    e.shop.setAttribute("transform", "translate(" + from.x + "," + from.y + ")");
    e.shopLabel.setAttribute("y", 32);
    e.home.setAttribute("transform", "translate(" + to.x + "," + to.y + ")");
    e.homeLabel.setAttribute("y", 32);

    drawProgress(rider);
  }

  /** อัปเดตเส้นทางส่วนที่วิ่งไปแล้ว + ตำแหน่งไรเดอร์ */
  function drawProgress(rider) {
    const e = rider.els;
    if (!rider.pathLength) return;

    const len = rider.pathLength;
    // stroke-dasharray แสดงเฉพาะช่วงที่วิ่งผ่านแล้ว
    e.done.setAttribute("stroke-dasharray", len * rider.progress + " " + len);

    const point = e.done.getPointAtLength(len * rider.progress);
    e.riderG.setAttribute("transform", "translate(" + point.x + "," + point.y + ")");
  }

  /** ลูปอนิเมชันกลางของทุกไรเดอร์ (rAF ตัวเดียว ไม่ใช่ตัวละคัน) */
  function startLoop() {
    if (rafHandle !== null) return;
    let last = performance.now();

    function tick(now) {
      const dt = now - last;
      last = now;

      let running = false;
      riders.forEach((rider) => {
        if (rider.done) return;
        running = true;
        const total = rider.minutes * MS_PER_MINUTE;
        rider.progress = Math.min(1, rider.progress + (dt * speed) / total);
        if (rider.progress >= 1) {
          rider.progress = 1;
          rider.done = true;
          onDelivered(rider);
        }
        drawProgress(rider);
        if (rider.id === selectedId) updateEtaCard(rider);
      });

      if (running) {
        rafHandle = requestAnimationFrame(tick);
      } else {
        rafHandle = null;
        refreshSidebar();
      }
    }
    rafHandle = requestAnimationFrame(tick);
  }

  function onDelivered(rider) {
    rider.els.routeGroup.classList.add("is-done");
    rider.els.markerGroup.classList.add("is-done");
    refreshSidebar();
  }

  function removeRider(id) {
    const idx = riders.findIndex((r) => r.id === id);
    if (idx < 0) return;
    const rider = riders[idx];
    rider.els.routeGroup.remove();
    rider.els.markerGroup.remove();
    riders.splice(idx, 1);

    if (selectedId === id) {
      if (riders.length) selectRider(riders[riders.length - 1].id);
      else clearSelection();
    }
    refreshSidebar();
  }

  /** โฟกัสไรเดอร์คนหนึ่ง: ซูมแผนที่ไปที่เส้นทางของเขา และวาดเมืองใหม่ */
  function selectRider(id) {
    const rider = riders.find((r) => r.id === id);
    if (!rider) return;
    selectedId = id;

    const o = rider.order;
    // การ์ด ETA ต้องโผล่ก่อน safeInsets() ถึงจะวัดขนาดมันได้
    show($("#eta-card"), true);
    syncMapSize();
    viewport = makeViewport(
      o.Restaurant_latitude, o.Restaurant_longitude,
      o.Delivery_location_latitude, o.Delivery_location_longitude
    );
    drawCity(rider.cityCode);

    // viewport เปลี่ยน -> ทุกคันต้องคำนวณตำแหน่งใหม่
    riders.forEach(layoutRider);

    // เน้นคันที่เลือก หรี่คันอื่น
    riders.forEach((r) => {
      const isSel = r.id === id;
      r.els.routeGroup.classList.toggle("is-dim", !isSel);
      r.els.markerGroup.classList.toggle("is-dim", !isSel);
      r.els.markerGroup.classList.toggle("marker--selected", isSel);
    });

    $("#map-city-name").textContent = rider.cityName;
    show($("#map-city"), true);
    updateEtaCard(rider);
    renderComparison(rider);
  }

  function clearSelection() {
    selectedId = null;
    show($("#eta-card"), false);
    show($("#map-city"), false);
    show($("#map-empty"), true);
    ["#layer-terrain", "#layer-blocks", "#layer-roads"].forEach((s) => ($(s).innerHTML = ""));
  }

  // --- ปุ่มความเร็ว ---
  $$(".speed__btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      speed = Number(btn.dataset.speed);
      $$(".speed__btn").forEach((b) => b.classList.toggle("is-active", b === btn));
    });
  });

  // --- ปุ่มล้างทั้งหมด ---
  $("#btn-clear").addEventListener("click", () => {
    riders.slice().forEach((r) => removeRider(r.id));
    history.length = 0;
    $("#history-list").innerHTML = "";
    renderHistoryScore();
  });

  // ===================================================================
  // 6) การ์ด ETA และแถบข้าง
  // ===================================================================
  function updateEtaCard(rider) {
    const o = rider.order;
    const card = $("#eta-card");
    const remaining = rider.minutes * (1 - rider.progress);

    $("#eta-avatar").textContent = VEHICLE_ICON[o.Type_of_vehicle] || "🛵";
    $("#eta-rider").textContent = o.Delivery_person_ID || "—";
    $("#eta-vehicle").textContent = o.Type_of_vehicle + " · " + o.Road_traffic_density;
    $("#eta-rating").textContent = "★ " + fmt(o.Delivery_person_Ratings, 1);

    $("#eta-remaining").textContent = rider.done ? "0.0" : fmt(remaining, 1);
    $("#eta-status").textContent = rider.done ? "ส่งถึงแล้ว 🎉" : "กำลังเดินทาง";
    $("#eta-actual").textContent = fmt(rider.actual, 1) + " นาที";
    $("#eta-distance").textContent =
      fmt(rider.result.derived_features.Distance_km, 2) + " กม.";

    $("#eta-progress").style.width = (rider.progress * 100).toFixed(1) + "%";
    card.classList.toggle("is-done", rider.done);
  }

  // ===================================================================
  // ประวัติผลเปรียบเทียบ
  // ===================================================================
  function pushHistory(rider) {
    const cmp = rider.result.comparison;
    const row = document.createElement("div");
    row.className = "hrow";
    row.dataset.rider = rider.id;

    const icon = !cmp ? "—" : cmp.winner === "tuned" ? "🟢" : cmp.winner === "baseline" ? "🔵" : "🤝";

    row.innerHTML =
      '<span class="hrow__idx">#' + rider.testIndex + "</span>" +
      '<span class="hrow__bar">' +
        '<span class="hrow__chip hrow__chip--truth">' + fmt(rider.actual, 0) + "</span>" +
        '<span class="hrow__chip hrow__chip--tuned">' + fmt(rider.result.tuned.predicted_minutes, 1) + "</span>" +
        '<span class="hrow__chip hrow__chip--baseline">' + fmt(rider.result.baseline.predicted_minutes, 1) + "</span>" +
      "</span>" +
      '<span class="hrow__win">' + icon + "</span>";

    row.title = "เฉลย " + fmt(rider.actual, 0) + " · Tuned " +
      fmt(rider.result.tuned.predicted_minutes, 1) + " · Baseline " +
      fmt(rider.result.baseline.predicted_minutes, 1);

    row.addEventListener("click", () => {
      if (riders.some((r) => r.id === rider.id)) selectRider(rider.id);
    });

    const list = $("#history-list");
    list.prepend(row);
    while (list.children.length > MAX_HISTORY) list.lastElementChild.remove();

    history.unshift({ winner: cmp ? cmp.winner : "tie" });
    while (history.length > MAX_HISTORY) history.pop();
    renderHistoryScore();
  }

  function renderHistoryScore() {
    const tuned = history.filter((h) => h.winner === "tuned").length;
    const base = history.filter((h) => h.winner === "baseline").length;
    $("#history-count").textContent = history.length;
    $("#history-score").textContent = "🟢 " + tuned + " – " + base + " 🔵";
    show($("#history"), history.length > 0);
  }

  function refreshSidebar() {
    const has = riders.length > 0;
    show($("#sidebar-empty"), !has);
    $("#btn-clear").disabled = !has;
    if (!has) {
      show($("#truth-card"), false);
      show($("#versus"), false);
      show($("#winner-badge"), false);
      show($("#btn-detail"), false);
      show($("#compare-warnings"), false);
      $("#sample-badge").textContent = "—";
    }
  }

  /** แสดงผลเปรียบเทียบของออเดอร์ที่เลือกอยู่ */
  function renderComparison(rider) {
    const r = rider.result;
    const cmp = r.comparison;

    $("#sample-badge").textContent = "#" + rider.testIndex + " / " + TESTSET_TOTAL;
    $("#truth-minutes").textContent = fmt(rider.actual, 1);
    $("#truth-src").textContent = "text.csv แถวที่ " + rider.testIndex + " · " + (r.order_id || "");
    show($("#truth-card"), true);

    renderSide("tuned", r.tuned, rider.actual, cmp);
    renderSide("baseline", r.baseline, rider.actual, cmp);
    show($("#versus"), true);

    // แถบสรุปผู้ชนะ
    const badge = $("#winner-badge");
    badge.classList.remove("is-tuned", "is-baseline", "is-tie");
    if (cmp) {
      badge.classList.add("is-" + cmp.winner);
      if (cmp.winner === "tie") {
        $("#winner-text").innerHTML = "ทั้งสองโมเดลทำนายห่างจากเฉลย <b>เท่ากัน</b>";
      } else {
        const label = cmp.winner === "tuned" ? "Tuned Model" : "Baseline Model";
        const other = cmp.winner === "tuned" ? "Baseline" : "Tuned";
        $("#winner-text").innerHTML =
          "<b>" + label + "</b> แม่นยำกว่า " + other + " อยู่ <b>" +
          fmt(cmp.accuracy_gap, 2) + "%</b> (ห่างจากเฉลยน้อยกว่า " +
          fmt(cmp.error_gap, 2) + " นาที)";
      }
      show(badge, true);
    } else {
      show(badge, false);
    }

    // คำเตือนจากโมเดล
    const warnBox = $("#compare-warnings");
    if (r.warnings && r.warnings.length) {
      warnBox.innerHTML = "<strong>ข้อควรระวัง</strong><ul>" +
        r.warnings.map((w) => "<li>" + escapeHtml(w) + "</li>").join("") + "</ul>";
      show(warnBox, true);
    } else {
      show(warnBox, false);
    }

    show($("#btn-detail"), true);
  }

  /** เติมค่าให้การ์ดโมเดลฝั่งหนึ่ง */
  function renderSide(key, side, actual, cmp) {
    const pred = side.predicted_minutes;
    $("#" + key + "-pred").textContent = fmt(pred, 1);

    // ส่วนต่างจากเฉลย: บวก = ทำนายช้ากว่าจริง, ลบ = เร็วกว่าจริง
    const diffEl = $("#" + key + "-diff");
    const diff = side.diff !== undefined && side.diff !== null ? side.diff : pred - actual;
    diffEl.classList.remove("is-over", "is-under", "is-exact");
    if (Math.abs(diff) < 0.05) {
      diffEl.textContent = "ตรงเฉลยพอดี";
      diffEl.classList.add("is-exact");
    } else {
      diffEl.textContent = (diff > 0 ? "+" : "") + fmt(diff, 1) + " นาที";
      diffEl.classList.add(diff > 0 ? "is-over" : "is-under");
    }

    const acc = side.accuracy_percent;
    $("#" + key + "-acc").textContent = acc === null || acc === undefined ? "—" : fmt(acc, 1) + "%";
    $("#" + key + "-bar").style.width = "0%";
    requestAnimationFrame(() => {
      $("#" + key + "-bar").style.width = Math.max(0, Math.min(100, acc || 0)) + "%";
    });

    const card = $("#card-" + key);
    const won = cmp && cmp.winner === key;
    card.classList.toggle("is-winner", Boolean(won));
    show($("#crown-" + key), Boolean(won));
  }

  // ===================================================================
  // 7) Modal รายละเอียด
  // ===================================================================
  const modal = $("#detail-modal");

  /** ป้ายกำกับภาษาไทยของแต่ละฟิลด์ดิบ */
  const FIELD_TH = {
    ID: "รหัสออเดอร์",
    Delivery_person_ID: "รหัสไรเดอร์",
    Delivery_person_Age: "อายุไรเดอร์ (ปี)",
    Delivery_person_Ratings: "คะแนนไรเดอร์",
    Restaurant_latitude: "ละติจูดร้าน",
    Restaurant_longitude: "ลองจิจูดร้าน",
    Delivery_location_latitude: "ละติจูดจุดส่ง",
    Delivery_location_longitude: "ลองจิจูดจุดส่ง",
    Order_Date: "วันที่สั่ง",
    Time_Orderd: "เวลาที่สั่ง",
    Time_Order_picked: "เวลาที่รับของ",
    Weather_conditions: "สภาพอากาศ",
    Road_traffic_density: "ความหนาแน่นจราจร",
    Vehicle_condition: "สภาพรถ (0–3)",
    Type_of_order: "ประเภทออเดอร์",
    Type_of_vehicle: "ยานพาหนะ",
    multiple_deliveries: "ออเดอร์พ่วง",
    Festival: "เทศกาล",
    City: "ลักษณะเมือง",
  };

  const RAW_ORDER = [
    "ID", "Delivery_person_ID", "Delivery_person_Age", "Delivery_person_Ratings",
    "Restaurant_latitude", "Restaurant_longitude",
    "Delivery_location_latitude", "Delivery_location_longitude",
    "Order_Date", "Time_Orderd", "Time_Order_picked",
    "Weather_conditions", "Road_traffic_density", "Vehicle_condition",
    "Type_of_order", "Type_of_vehicle", "multiple_deliveries", "Festival", "City",
  ];

  function row(label, value, accent) {
    return (
      "<tr><th>" + escapeHtml(label) + "</th>" +
      '<td class="' + (accent ? "is-accent" : "") + '">' + escapeHtml(String(value)) + "</td></tr>"
    );
  }

  function openDetail(riderId) {
    const rider = riders.find((r) => r.id === riderId);
    if (!rider) return;

    const o = rider.order;
    const p = rider.result;
    const d = p.derived_features;
    const cmp = p.comparison;

    $("#modal-title").textContent = "Test Sample #" + rider.testIndex + " · " + (o.ID || "—");
    $("#modal-sub").textContent =
      "text.csv แถวที่ " + rider.testIndex + " / " + TESTSET_TOTAL +
      " · " + (o.Delivery_person_ID || "");

    // สรุปเปรียบเทียบ
    $("#d-eta").textContent = fmt(rider.actual, 1);
    $("#d-tuned").textContent =
      fmt(p.tuned.predicted_minutes, 1) + " นาที (ห่าง " + fmt(p.tuned.error, 2) + ")";
    $("#d-baseline").textContent =
      fmt(p.baseline.predicted_minutes, 1) + " นาที (ห่าง " + fmt(p.baseline.error, 2) + ")";
    $("#d-winner").textContent = cmp ? cmp.better_model : "—";

    // คำเตือนจากโมเดล (ถ้ามี)
    const warnBox = $("#d-warnings");
    if (p.warnings && p.warnings.length) {
      warnBox.innerHTML =
        "<strong>ข้อควรระวัง</strong><ul>" +
        p.warnings.map((w) => "<li>" + escapeHtml(w) + "</li>").join("") + "</ul>";
      show(warnBox, true);
    } else {
      show(warnBox, false);
    }

    // ข้อมูลดิบ 19 ฟิลด์
    $("#d-raw").innerHTML = RAW_ORDER
      .map((key) => row(FIELD_TH[key] || key, o[key]))
      .join("");

    // ฟีเจอร์ที่โมเดลคำนวณต่อ
    $("#d-derived").innerHTML = [
      row("Distance_km — ระยะทาง Haversine", fmt(d.Distance_km, 4) + " กม.", true),
      row("Prep_time_min — เวลาเตรียมอาหาร", fmt(d.Prep_time_min, 0) + " นาที", true),
      row("Order_hour — ชั่วโมงที่สั่ง", d.Order_hour + ":00 น."),
      row("Order_period — ช่วงเวลา", PERIOD_TH[d.Order_period] || d.Order_period),
      row("Order_dayofweek — วันในสัปดาห์", DAY_TH[d.Order_dayofweek] || d.Order_dayofweek),
      row("Is_weekend — เป็นวันหยุด", d.Is_weekend ? "ใช่" : "ไม่ใช่"),
    ].join("");

    // ปัจจัยสำคัญ (โครงสร้างใหม่ไม่ได้ส่ง top_factors มา จึงซ่อนบล็อกนี้ถ้าไม่มี)
    const factors = p.top_factors || [];
    const maxImp = factors.length ? Math.max(...factors.map((f) => f.importance)) : 1;
    $("#d-factors").innerHTML = factors
      .map(
        (f) =>
          "<li>" +
          '<div class="factor__row">' +
            '<span class="factor__name">' + escapeHtml(f.feature) + "</span>" +
            '<span class="factor__value">ค่า ' + f.value + " · น้ำหนัก " + (f.importance * 100).toFixed(1) + "%</span>" +
          "</div>" +
          '<div class="factor__bar"><div class="factor__fill" data-w="' +
            ((f.importance / maxImp) * 100).toFixed(1) + '"></div></div>' +
          "</li>"
      )
      .join("");

    // /compare ไม่ได้ส่ง top_factors มา (เป็นค่าของโมเดลโดยรวม ไม่ใช่ของออเดอร์นี้)
    const factorBlock = $("#d-factors").closest(".mblock");
    if (factorBlock) show(factorBlock, factors.length > 0);

    show(modal, true);
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => {
      $$("#d-factors .factor__fill").forEach((el) => (el.style.width = el.dataset.w + "%"));
    });
  }

  function closeDetail() {
    show(modal, false);
    document.body.style.overflow = "";
  }

  $("#btn-detail").addEventListener("click", () => {
    if (selectedId !== null) openDetail(selectedId);
  });

  modal.addEventListener("click", (event) => {
    if (event.target.hasAttribute("data-close")) closeDetail();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!benchModal.hidden) closeBench();
    else if (!modal.hidden) closeDetail();
  });

  // ===================================================================
  // 7.5) Benchmark ทั้งชุด 1,000 แถว
  // ===================================================================
  const benchModal = $("#bench-modal");
  const btnBenchmark = $("#btn-benchmark");
  let benchCache = null;   // ผลล่าสุด เปิดซ้ำไม่ต้องรันใหม่

  $("#bench-total").textContent = TESTSET_TOTAL.toLocaleString("th-TH");

  btnBenchmark.addEventListener("click", async () => {
    show(benchModal, true);
    document.body.style.overflow = "hidden";
    show($("#bench-error"), false);

    // มีผลเดิมอยู่แล้ว -> แสดงเลย ไม่ต้องรันซ้ำ
    if (benchCache) {
      renderBenchmark(benchCache);
      return;
    }

    show($("#bench-body"), false);
    show($("#bench-loading"), true);
    $("#bench-sub").textContent = "กำลังประเมิน " + TESTSET_TOTAL.toLocaleString("th-TH") + " แถว…";
    btnBenchmark.disabled = true;

    try {
      const data = await apiFetch("/api/evaluate-batch/", {
        method: "POST",
        body: JSON.stringify({}),
      });
      benchCache = data;
      renderBenchmark(data);
      setBackendStatus(true, "โมเดลพร้อม");
    } catch (err) {
      show($("#bench-loading"), false);
      const box = $("#bench-error");
      box.textContent = err.message;
      show(box, true);
      $("#bench-sub").textContent = "ประเมินไม่สำเร็จ";
      setBackendStatus(false, "โมเดลมีปัญหา");
    } finally {
      btnBenchmark.disabled = false;
    }
  });

  function renderBenchmark(d) {
    show($("#bench-loading"), false);

    $("#bench-sub").textContent =
      d.source + " · ใช้เวลา " + fmt(d.elapsed_seconds, 2) + " วินาที";
    $("#bench-meta").textContent =
      "ประเมิน " + d.evaluated.toLocaleString("th-TH") + " แถว" +
      (d.skipped && d.skipped.length ? " · ข้าม " + d.skipped.length + " แถว" : "");

    // ---- แถบผู้ชนะรวม ----
    const badge = $("#bench-winner");
    badge.classList.remove("is-tuned", "is-baseline", "is-tie");
    badge.classList.add("is-" + d.overall_winner);
    if (d.overall_winner === "tie") {
      $("#bench-winner-text").innerHTML = "ทั้งสองโมเดลได้ MAE <b>เท่ากัน</b>";
    } else {
      const label = d.overall_winner === "tuned" ? "Tuned Model" : "Baseline Model";
      const other = d.overall_winner === "tuned" ? "Baseline" : "Tuned";
      const impr = Math.abs(d.mae_improvement_percent);
      $("#bench-winner-text").innerHTML =
        "<b>" + label + "</b> แม่นยำกว่า " + other + " โดยรวม — " +
        "ค่าความคลาดเคลื่อนเฉลี่ยต่ำกว่า <b>" + fmt(impr, 2) + "%</b>";
    }

    // ---- ตารางเปรียบเทียบ ----
    // lowerIsBetter: true = ค่าน้อยกว่าดีกว่า
    const ROWS = [
      { key: "MAE", label: "MAE — ค่าความคลาดเคลื่อนเฉลี่ย", unit: " นาที", digits: 4, lower: true },
      { key: "RMSE", label: "RMSE — ให้น้ำหนักกับความผิดพลาดใหญ่", unit: "", digits: 4, lower: true },
      { key: "R2", label: "R² — อธิบายความผันแปรได้เท่าไร", unit: "", digits: 4, lower: false },
      { key: "mean_accuracy_percent", label: "ความแม่นยำเฉลี่ย", unit: "%", digits: 2, lower: false },
    ];

    $("#bench-rows").innerHTML = ROWS.map((row) => {
      const t = d.tuned[row.key];
      const b = d.baseline[row.key];
      const tBetter = row.lower ? t < b : t > b;
      const bBetter = row.lower ? b < t : b > t;
      const verdict = tBetter ? "🟢 Tuned" : bBetter ? "🔵 Baseline" : "เสมอ";
      return (
        "<tr>" +
        "<td>" + escapeHtml(row.label) + "</td>" +
        '<td class="' + (tBetter ? "is-best" : "") + '">' + fmt(t, row.digits) + row.unit + "</td>" +
        '<td class="' + (bBetter ? "is-best" : "") + '">' + fmt(b, row.digits) + row.unit + "</td>" +
        '<td class="is-verdict">' + verdict + "</td>" +
        "</tr>"
      );
    }).join("");

    // ---- Win rate ----
    const w = d.win_rate;
    $("#win-tuned").textContent = w.tuned_wins + " (" + fmt(w.tuned_win_percent, 1) + "%)";
    $("#win-baseline").textContent = w.baseline_wins + " (" + fmt(w.baseline_win_percent, 1) + "%)";
    $("#win-tie").textContent = w.ties + " (" + fmt(w.tie_percent, 1) + "%)";

    const segs = [
      ["#winbar-tuned", w.tuned_win_percent, w.tuned_wins],
      ["#winbar-tie", w.tie_percent, w.ties],
      ["#winbar-baseline", w.baseline_win_percent, w.baseline_wins],
    ];
    segs.forEach(([sel, pct]) => ($(sel).style.width = "0%"));
    requestAnimationFrame(() => {
      segs.forEach(([sel, pct, count]) => {
        const el = $(sel);
        el.style.width = pct + "%";
        el.textContent = pct >= 12 ? fmt(pct, 1) + "%" : "";
        el.title = count + " แถว (" + fmt(pct, 1) + "%)";
      });
    });

    // ---- หมายเหตุตีความ ----
    const gap = Math.abs(d.accuracy_gap);
    $("#bench-note").textContent =
      gap < 1
        ? "หมายเหตุ: ผลต่างความแม่นยำเฉลี่ยอยู่ที่ " + fmt(gap, 2) +
          "% เท่านั้น ถือว่าสองโมเดลทำได้ใกล้เคียงกันมาก " +
          "การปรับจูน hyperparameter ในงานนี้ช่วยได้เพียงเล็กน้อย"
        : "ผลต่างความแม่นยำเฉลี่ย " + fmt(gap, 2) + "%";

    show($("#bench-body"), true);
  }

  function closeBench() {
    show(benchModal, false);
    document.body.style.overflow = "";
  }

  benchModal.addEventListener("click", (event) => {
    if (event.target.hasAttribute("data-close-bench")) closeBench();
  });

  // ===================================================================
  // 8) สถานะ Backend
  // ===================================================================
  const statusPill = $("#status-pill");

  function setBackendStatus(online, text) {
    statusPill.classList.remove("is-checking");
    statusPill.classList.toggle("is-online", online);
    statusPill.classList.toggle("is-offline", !online);
    $("#status-text").textContent = text;
  }

  statusPill.addEventListener("click", async () => {
    statusPill.classList.add("is-checking");
    $("#status-text").textContent = "กำลังตรวจสอบ…";
    try {
      const data = await apiFetch("/api/health/");
      setBackendStatus(Boolean(data.online), data.online ? "โมเดลพร้อม" : "โมเดลยังไม่พร้อม");
    } catch (err) {
      setBackendStatus(false, "โมเดลออฟไลน์");
    }
  });

  // ย่อ/ขยายหน้าต่าง -> viewBox และพื้นที่ปลอดภัยเปลี่ยน ต้องวางตำแหน่งใหม่ทั้งหมด
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    if (!riders.length) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const rider = riders.find((r) => r.id === selectedId);
      if (rider) selectRider(rider.id);
    }, 160);
  });

  // ===================================================================
  // เริ่มต้น
  // ===================================================================
  syncMapSize();
  refreshSidebar();
  renderHistoryScore();
})();
