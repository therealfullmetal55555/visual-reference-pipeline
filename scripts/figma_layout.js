/**
 * Figma Modular Reference Layout Generator
 * 
 * Runs in Figma Desktop DevTools Console (⌥ + ⌘ + I) or as a lightweight Figma Plugin.
 * Procedurally creates 2000×1650 dark theme frames (#0E0E0E), calculates 3-column
 * modular grids, scales images preserving native aspect ratios, and generates
 * typography captions and section headers.
 */

(async () => {
  // 1. Load system typography
  await figma.loadFontAsync({ family: "Inter", style: "Medium" });
  await figma.loadFontAsync({ family: "Inter", style: "Regular" });

  // 2. Layout & category configuration
  const categories = [
    {
      name: "FASHION И ТЕЛЕСНАЯ ДРАМАТУРГИЯ",
      prefixes: ["[Fashion]"],
      x: 7840
    },
    {
      name: "VVUTURA, CARTI BILLBOARD И ОБЪЕКТЫ",
      prefixes: ["[Editorial]", "[Biomechanics]", "[Object]"],
      x: 9940
    },
    {
      name: "ГРАФИЧЕСКИЙ ЗНАК, МЕРЧ И ПРИНТ",
      prefixes: ["[Graphic]", "[Typography]"],
      x: 12040
    },
    {
      name: "АНАТОМИЧЕСКАЯ КАЛЛИГРАФИЯ И ТАТУ",
      prefixes: ["[Lettering]"],
      x: 14140
    },
    {
      name: "СЦЕНОГРАФИЯ И СВЕТОВАЯ АРХИТЕКТУРА",
      prefixes: ["[Stage]"],
      x: 16240
    },
    {
      name: "ЛИЧНОЕ ПРИСУТСТВИЕ, VHS И ВИДЕОКАДР",
      prefixes: ["[Presence]", "[Document]", "[Video Still]"],
      x: 18340
    }
  ];

  const page = figma.currentPage;
  const allNodes = [...page.children];

  console.log(`[Figma Layout] Scanning page: ${allNodes.length} root elements found.`);

  // 3. Process each category into a standalone modular frame
  for (const cat of categories) {
    const matchingNodes = allNodes.filter(n => 
      cat.prefixes.some(p => n.name && n.name.startsWith(p))
    );

    if (matchingNodes.length === 0) {
      console.log(`[-] Skipping category ${cat.name}: no matching layers.`);
      continue;
    }

    // Create presentation frame (matching 2000×1650 canvas standard)
    const frame = figma.createFrame();
    frame.name = cat.name;
    frame.resize(2000, 1650);
    frame.x = cat.x;
    frame.y = 0;
    frame.fills = [{ type: 'SOLID', color: { r: 14 / 255, g: 14 / 255, b: 14 / 255 } }];
    frame.clipsContent = true;

    // Section title
    const title = figma.createText();
    title.fontName = { family: "Inter", style: "Medium" };
    title.characters = cat.name;
    title.fontSize = 24;
    title.fills = [{ type: 'SOLID', color: { r: 0.9, g: 0.9, b: 0.9 } }];
    title.x = 80;
    title.y = 80;
    frame.appendChild(title);

    // 3-Column modular grid metrics
    const startX = 80;
    const startY = 160;
    const cardW = 560;
    const cardMaxH = 500;
    const gapX = 60;
    const gapY = 80;

    matchingNodes.forEach((node, idx) => {
      const col = idx % 3;
      const row = Math.floor(idx / 3);
      const posX = startX + col * (cardW + gapX);
      const posY = startY + row * (cardMaxH + gapY);

      // Preserve native aspect ratio
      const origW = node.width || cardW;
      const origH = node.height || cardMaxH;
      const scale = Math.min(cardW / origW, (cardMaxH - 50) / origH);
      const newW = Math.round(origW * scale);
      const newH = Math.round(origH * scale);
      node.resize(newW, newH);

      node.x = posX;
      node.y = posY;
      frame.appendChild(node);

      // Typographic label
      const cap = figma.createText();
      cap.fontName = { family: "Inter", style: "Regular" };
      const cleanName = node.name.replace(/^\[[^\]]+\]\s*/, '').replace(/\.(jpg|png|webp)$/i, '');
      cap.characters = cleanName;
      cap.fontSize = 14;
      cap.fills = [{ type: 'SOLID', color: { r: 0.6, g: 0.6, b: 0.6 } }];
      cap.x = posX;
      cap.y = posY + newH + 12;
      frame.appendChild(cap);
    });

    console.log(`[✓] Created frame "${cat.name}" with ${matchingNodes.length} cards.`);
  }

  // 4. Handle atmosphere assets into existing Mister Dove frame
  const atmoNodes = allNodes.filter(n => n.name && n.name.startsWith('[Atmosphere]'));
  const mdFrame = page.children.find(n => n.name && n.name.includes('Mister Dove'));
  if (mdFrame && atmoNodes.length > 0) {
    atmoNodes.forEach((node, idx) => {
      node.resize(560, 420);
      node.x = 80 + idx * 620;
      node.y = 1050;
      mdFrame.appendChild(node);
    });
    console.log(`[✓] Appended ${atmoNodes.length} atmosphere layers to Mister Dove frame.`);
  }

  figma.notify("✨ Сетка референсов успешно выстроена!");
})();
