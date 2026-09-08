/**
 * Table of contents and side navigation (sidebar).
 * Pure functions / local DOM: the only app dependency is the selection callback.
 */

const PART_ONE_TITLE = 'Part One · The Concept of Imbalances';

/** Strip the " (continued N/M)" suffix from a section title. */
function baseTitle(t) {
    return (t || '').replace(/ \(continued \d+\/\d+\)$/, '');
}

/**
 * Parse an explicit Part section title such as:
 *   "Part Two / Minor Pieces — Knights (continued 1/2)"
 * into { partWord, partName, subName, base }.
 * Returns null if the title is not a Part label.
 */
function parsePartTitle(title) {
    const m = (title || '').match(
        /^Part\s+(\w+)\s*\/\s*(.+?)(?:\s*[\u2014\u2013-]\s*(.+?))?(?:\s*\(continued\s+\d+\/\d+\))?$/
    );
    if (!m) return null;
    const partWord = m[1];
    const partName = m[2].trim();
    const subName = m[3] ? m[3].trim() : null;
    return { partWord, partName, subName, base: subName || partName };
}

/** Group consecutive L2 sections by base title. */
function groupSectionsIntoChapters(sectionList) {
    if (!sectionList.length) return [];
    const groups = [];
    let current = null;
    for (const s of sectionList) {
        const base = baseTitle(s.title);
        if (!current || current.base !== base) {
            current = { base, sections: [s] };
            groups.push(current);
        } else {
            current.sections.push(s);
        }
    }
    return groups.map(g => ({
        type: 'chapter',
        title: g.sections.length > 1
            ? `${g.base} (${g.sections.length} sections)`
            : g.base,
        page: g.sections[0].section_num,
        children: g.sections.map(s => ({ type: 'section', title: s.title, page: s.section_num })),
    }));
}

/**
 * Build the TOC tree from the book sections.
 *
 * The EPUB spine places Part recap sections *after* their chapter content, so
 * we reconstruct an ebook-like hierarchy:
 *   Front matter (L1 sections before the first chapter)
 *   Part One     (all L2 sections before the first explicit Part label)
 *   Part Two · X … Part Nine · Y (explicit Part labels, grouped by sub-topic)
 *   Back matter  (L2 sections after the last explicit Part label)
 */
export function buildTOCFromSections(bookData) {
    if (!bookData || !bookData.sections) return [];
    const sections = bookData.sections;
    const toc = [];
    let i = 0;

    // Front matter: leading L1 sections that are not Part labels.
    const frontMatter = [];
    while (i < sections.length) {
        const s = sections[i];
        if (s.level !== 1 || parsePartTitle(s.title)) break;
        frontMatter.push(s);
        i++;
    }
    if (frontMatter.length) {
        toc.push({
            type: 'part',
            title: 'Front matter',
            page: frontMatter[0].section_num,
            children: frontMatter.map(s => ({
                type: 'chapter',
                title: s.title,
                page: s.section_num,
                children: [{ type: 'section', title: s.title, page: s.section_num }],
            })),
        });
    }

    // Part One: implicit part covering all L2 sections before the first explicit Part label.
    const partOneSections = [];
    while (i < sections.length && !(sections[i].level === 1 && parsePartTitle(sections[i].title))) {
        if (sections[i].level === 2) partOneSections.push(sections[i]);
        i++;
    }
    if (partOneSections.length) {
        toc.push({
            type: 'part',
            title: PART_ONE_TITLE,
            page: partOneSections[0].section_num,
            children: groupSectionsIntoChapters(partOneSections),
        });
    }

    // Explicit Parts (Two … Nine), grouped by (partWord, subName).
    while (i < sections.length) {
        const s = sections[i];
        if (s.level !== 1) break;
        const parsed = parsePartTitle(s.title);
        if (!parsed) break;

        const partWord = parsed.partWord;
        const subName = parsed.subName;
        const chapterTitle = parsed.base;
        const group = [s];
        i++;
        while (i < sections.length) {
            const next = sections[i];
            if (next.level !== 1) break;
            const np = parsePartTitle(next.title);
            if (!np || np.partWord !== partWord || (np.subName || '') !== (subName || '')) break;
            group.push(next);
            i++;
        }

        toc.push({
            type: 'part',
            title: `Part ${partWord} · ${chapterTitle}`,
            page: group[0].section_num,
            children: [{
                type: 'chapter',
                title: group.length > 1
                    ? `${chapterTitle} (${group.length} sections)`
                    : chapterTitle,
                page: group[0].section_num,
                children: group.map(s => ({ type: 'section', title: s.title, page: s.section_num })),
            }],
        });
    }

    // Back matter: remaining L2 sections after the last explicit Part label.
    const backMatter = [];
    while (i < sections.length) {
        if (sections[i].level === 2) backMatter.push(sections[i]);
        i++;
    }
    if (backMatter.length) {
        toc.push({
            type: 'part',
            title: 'Back matter',
            page: backMatter[0].section_num,
            children: groupSectionsIntoChapters(backMatter),
        });
    }

    return toc;
}

/**
 * Build the navigation tree from the native NCX TOC (toc.json).
 *
 * The NCX tree is rendered as-is: part -> chapter -> section following the
 * navPoint depth, with the published titles (no artificial " (N sections)"
 * grouping). Leaf nodes become clickable sections (carrying their section
 * number and, when present, their NCX anchor); non-leaf nodes stay
 * collapsible headers.
 */
export function buildTOCFromNCX(ncxTree) {
    if (!Array.isArray(ncxTree) || !ncxTree.length) return [];
    const toNav = (node, depth) => {
        const hasChildren = Array.isArray(node.children) && node.children.length > 0;
        // Skip dead leaves with no book section (e.g. Copyright, Contents):
        // they would render as non-clickable text.
        if (!hasChildren && typeof node.section !== 'number') return null;
        const navNode = {
            type: hasChildren ? (depth === 1 ? 'part' : 'chapter') : 'section',
            title: node.title,
            page: (typeof node.section === 'number') ? node.section : null,
            anchor: node.anchor || null,
        };
        if (hasChildren) {
            navNode.children = node.children.map((child) => toNav(child, depth + 1)).filter(Boolean);
            // A header left with no navigable children is dead too — drop it
            // rather than rendering an empty toggle.
            if (!navNode.children.length && navNode.page === null) return null;
        }
        return navNode;
    };
    return ncxTree.map((node) => toNav(node, 1)).filter(Boolean);
}

/** Render the navigation tree; onSelect(section, anchor) is called on click. */
export function renderNavigation(navTree, toc, onSelect) {
    navTree.innerHTML = '';
    if (!toc || !toc.length) {
        navTree.innerHTML = '<div class="nav-item section">No data available</div>';
        return;
    }

    const handleSelect = (section, anchor) => {
        onSelect(section, anchor);
        closeSidebarMobile();
    };

    const createHeader = (node) => {
        const header = document.createElement('div');
        header.className = 'nav-header';
        header.setAttribute('role', 'button');
        header.setAttribute('tabindex', '0');
        header.setAttribute('aria-expanded', 'false');
        // Single chevron: rotation is handled by CSS when expanded.
        header.innerHTML = `<span class="nav-toggle" aria-hidden="true">▸</span><span class="nav-title">${node.title}</span>`;
        return header;
    };

    const isNavigable = (node) =>
        node.page !== null && node.page !== undefined && !Number.isNaN(node.page);

    const renderNode = (node) => {
        const el = document.createElement('div');
        el.className = `nav-item ${node.type}`;
        if (isNavigable(node)) {
            el.dataset.section = String(node.page);
        }

        if (node.type === 'section') {
            el.textContent = node.title;
            if (isNavigable(node)) {
                if (node.anchor) el.dataset.anchor = node.anchor;
                el.setAttribute('role', 'button');
                el.setAttribute('tabindex', '0');
                const select = () => handleSelect(node.page, node.anchor || null);
                el.addEventListener('click', select);
                el.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        select();
                    }
                });
            }
            return el;
        }

        const header = createHeader(node);
        el.appendChild(header);

        if (!node.children || !node.children.length) return el;

        const childrenContainer = document.createElement('div');
        childrenContainer.className = 'nav-children';
        for (const child of node.children) {
            childrenContainer.appendChild(renderNode(child));
        }
        el.appendChild(childrenContainer);

        header.addEventListener('click', (e) => {
            e.stopPropagation();
            const expanded = childrenContainer.classList.toggle('expanded');
            header.setAttribute('aria-expanded', String(expanded));
            // A header with a resolvable section navigates there too (e.g.
            // a chapter intro without a dedicated leaf); headers without a
            // section (Title Page, Parts, Answers...) stay pure toggles.
            if (isNavigable(node)) {
                handleSelect(node.page, node.anchor || null);
            }
        });
        header.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                header.click();
            }
        });

        return el;
    };

    const fragment = document.createDocumentFragment();
    for (const part of toc) fragment.appendChild(renderNode(part));
    navTree.appendChild(fragment);
}

/** Open or close the sidebar and sync the scrim + menu button. */export function setSidebarOpen(isOpen) {
    const sidebar = document.getElementById('sidebar');
    const scrim = document.getElementById('sidebar-scrim');
    const toggle = document.getElementById('menu-toggle');
    if (!sidebar) return;
    sidebar.classList.toggle('hidden', !isOpen);
    // The scrim is a mobile-only overlay: on desktop the sidebar sits
    // side-by-side with the content, so the scrim must stay hidden even
    // when the sidebar is open. Without this, reopening the sidebar on
    // desktop leaves a dark overlay over everything.
    const isMobile = window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
    if (scrim) scrim.setAttribute('aria-hidden', String(!(isOpen && isMobile)));
    if (toggle) toggle.setAttribute('aria-expanded', String(isOpen));
}

/** Close the sidebar on mobile (after clicking an item). */
export function closeSidebarMobile() {
    if (window.matchMedia('(max-width: 768px)').matches) {
        setSidebarOpen(false);
    }
}

/** Highlight the navigation entry for the current section (and anchor). */
export function markActiveNavItem(currentSection, anchor = null, scrollIntoView = true) {
    let hasLeafMatch = false;
    document.querySelectorAll('.nav-item.section').forEach((el) => {
        const sameSection = parseInt(el.dataset.section, 10) === currentSection;
        const sameAnchor = !anchor || el.dataset.anchor === anchor;
        const active = sameSection && sameAnchor;
        el.classList.toggle('active', active);
        if (active) hasLeafMatch = true;
    });

    // Header-level highlight only when no leaf matches (e.g. the current
    // section is a chapter intro). Leaves take precedence so several
    // anchors of the same section don't light up all their siblings.
    if (!hasLeafMatch) {
        document.querySelectorAll('.nav-item:not(.section)').forEach((el) => {
            const sameSection = parseInt(el.dataset.section, 10) === currentSection;
            el.classList.toggle('active', sameSection);
        });
    }

    const selector = anchor
        ? `.nav-item.section[data-section="${currentSection}"][data-anchor="${anchor}"]`
        : `.nav-item.section[data-section="${currentSection}"]`;
    let activeEl = document.querySelector(selector);
    if (!activeEl && !anchor && !hasLeafMatch) {
        activeEl = document.querySelector(`.nav-item:not(.section)[data-section="${currentSection}"]`);
    }
    if (!activeEl) return;

    // Ensure all ancestor parts/chapters are expanded so the active item is visible.
    let parent = activeEl.parentElement;
    while (parent) {
        if (parent.classList && parent.classList.contains('nav-children')) {
            parent.classList.add('expanded');
            const header = parent.previousElementSibling;
            if (header) {
                header.setAttribute('aria-expanded', 'true');
            }
        }
        parent = parent.parentElement;
    }

    if (scrollIntoView) {
        activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}
