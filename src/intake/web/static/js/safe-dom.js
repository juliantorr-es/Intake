/**
 * Safe DOM manipulation utilities.
 * NEVER use innerHTML for user-controlled content.
 * Always use textContent or explicitly created elements.
 */

/**
 * Create an element with the given tag, attributes, and children.
 * @param {string} tag - The HTML tag name
 * @param {Object} [attrs] - Attributes to set on the element
 * @param {...Node} [children] - Child nodes to append
 * @returns {HTMLElement} The created element
 */
export function createElement(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    
    // Set attributes safely
    for (const [key, value] of Object.entries(attrs)) {
        if (key.startsWith('data-') || key === 'class' || key === 'id' || key === 'type') {
            el.setAttribute(key, String(value));
        } else {
            el[key] = value;
        }
    }
    
    // Append children safely
    for (const child of children) {
        if (child === null || child === undefined) continue;
        if (typeof child === 'string') {
            el.appendChild(document.createTextNode(child));
        } else if (child instanceof Node) {
            el.appendChild(child);
        }
    }
    
    return el;
}

/**
 * Set the text content of an element safely.
 * @param {HTMLElement} element - The element to set text on
 * @param {string} text - The text to set
 */
export function setTextContent(element, text) {
    element.textContent = text;
}

/**
 * Create a text node safely.
 * @param {string} text - The text content
 * @returns {Text} The text node
 */
export function createText(text) {
    return document.createTextNode(text);
}

/**
 * Safely escape HTML special characters in a string.
 * @param {string} str - The string to escape
 * @returns {string} The escaped string
 */
export function escapeHtml(str) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '/': '&#x2F;'
    };
    return str.replace(/[&<>"'/]/g, m => map[m]);
}

/**
 * Create a DOM fragment from a template string WITHOUT using innerHTML.
 * This is a safe alternative to element.innerHTML = template.
 * @param {string} template - The template string
 * @returns {DocumentFragment} The fragment
 */
export function safeTemplate(template) {
    const fragment = document.createDocumentFragment();
    const tempDiv = document.createElement('div');
    
    // Parse the template text nodes and elements
    const parser = new DOMParser();
    const doc = parser.parseFromString(template, 'text/html');
    
    // Move all children to fragment
    while (doc.body.firstChild) {
        fragment.appendChild(doc.body.firstChild);
    }
    
    return fragment;
}

/**
 * URL allowlist for safe navigation.
 * @type {Set<string>}
 */
export const SAFE_URL_ORIGINS = new Set([
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    window.location.origin
]);

/**
 * Check if a URL is safe to navigate to.
 * @param {string} url - The URL to check
 * @returns {boolean} Whether the URL is safe
 */
export function isSafeUrl(url) {
    try {
        const parsed = new URL(url);
        return SAFE_URL_ORIGINS.has(parsed.origin);
    } catch {
        return false;
    }
}

/**
 * Safely navigate to a URL if it's in the allowlist.
 * @param {string} url - The URL to navigate to
 */
export function safeNavigate(url) {
    if (isSafeUrl(url)) {
        window.location.href = url;
    } else {
        console.error('Blocked navigation to unsafe URL:', url);
    }
}

/**
 * Create a safe anchor element.
 * @param {string} href - The URL
 * @param {string} text - The link text
 * @param {Object} [attrs] - Additional attributes
 * @returns {HTMLAnchorElement} The anchor element
 */
export function createSafeLink(href, text, attrs = {}) {
    if (!isSafeUrl(href)) {
        console.error('Blocked creation of link to unsafe URL:', href);
        return createElement('span', { class: 'unsafe-link' }, text);
    }
    return createElement('a', { href, ...attrs }, text);
}

/**
 * Remove all children from an element.
 * @param {HTMLElement} element - The element to clear
 */
export function clearElement(element) {
    while (element.firstChild) {
        element.removeChild(element.firstChild);
    }
}

/**
 * Replace an element's children with new content.
 * @param {HTMLElement} element - The element to replace content in
 * @param {...Node} content - The new content
 */
export function replaceContent(element, ...content) {
    clearElement(element);
    for (const item of content) {
        if (item === null || item === undefined) continue;
        if (typeof item === 'string') {
            element.appendChild(document.createTextNode(item));
        } else if (item instanceof Node) {
            element.appendChild(item);
        }
    }
}
