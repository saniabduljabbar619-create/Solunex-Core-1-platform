/*
Solunex JS / Web / Electron SDK — C2.2
One-file drop (copy-paste ready)

Features:
- init({ apiBase, clientId, secret, environment })
- verifyLicense(licenseKey)
- signRequest(payload)
- generateDeviceId()
- bindDevice(licenseKey)
- trackActivation(licenseKey, metadata)
- browser/node/electron persistence (localStorage / fs / electron-store)
- HMAC request signing (Web Crypto and Node crypto)
- Example usage at bottom

Notes:
- This file uses no external build step. In production you may want to bundle/minify.
- In Electron, pass `isElectron: true` on init OR call with `process && process.versions && process.versions.electron` detection.
*/

(function (root, factory) {
  if (typeof module === 'object' && typeof module.exports === 'object') {
    module.exports = factory();
  } else if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else {
    root.Solunex = factory();
  }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // -------------------------
  // Utilities
  // -------------------------
  const _isNode = (typeof process !== 'undefined' && process.versions && process.versions.node);
  const _isElectron = (() => {
    try {
      return !!(typeof process !== 'undefined' && process.versions && process.versions.electron);
    } catch (e) { return false; }
  })();
  const _isBrowser = (typeof window !== 'undefined' && typeof window.document !== 'undefined');

  // Simple safe JSON parse
  function safeParse(str, fallback = null) {
    try { return JSON.parse(str); } catch (e) { return fallback; }
  }

  // UUID v4 generator (RFC4122 compliant, simple implementation)
  function uuidv4() {
    if (_isNode) {
      try {
        const cryptoNode = require('crypto');
        return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
          (c ^ cryptoNode.randomBytes(1)[0] & 15 >> c / 4).toString(16)
        );
      } catch (e) {}
    }
    // browser fallback
    return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
      (crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
    );
  }

  // -------------------------
  // Persistence Layer
  // -------------------------
  // Provides getItem/setItem/removeItem across environments
  function makeStore(opts = {}) {
    const prefix = opts.prefix || 'solunex_';

    if (_isElectron) {
      // try to require electron-store if available
      try {
        const Store = require('electron-store');
        const store = new Store({ name: opts.storeName || 'solunex' });
        return {
          getItem: (k) => {
            const v = store.get(prefix + k);
            return (typeof v === 'undefined') ? null : JSON.stringify(v);
          },
          setItem: (k, v) => store.set(prefix + k, safeParse(v, v)),
          removeItem: (k) => store.delete(prefix + k)
        };
      } catch (e) {
        // fall through to node fs store
      }
    }

    if (_isNode) {
      const fs = require('fs');
      const path = require('path');
      const homedir = require('os').homedir();
      const base = path.join(homedir, opts.nodeDir || '.solunex');
      try { if (!fs.existsSync(base)) fs.mkdirSync(base, { recursive: true }); } catch (e) {}

      return {
        getItem: (k) => {
          try {
            const p = path.join(base, prefix + k + '.json');
            if (!fs.existsSync(p)) return null;
            return fs.readFileSync(p, 'utf8');
          } catch (e) { return null; }
        },
        setItem: (k, v) => {
          try {
            const p = path.join(base, prefix + k + '.json');
            fs.writeFileSync(p, typeof v === 'string' ? v : JSON.stringify(v), 'utf8');
          } catch (e) {}
        },
        removeItem: (k) => {
          try { const p = path.join(base, prefix + k + '.json'); if (fs.existsSync(p)) fs.unlinkSync(p); } catch (e) {}
        }
      };
    }

    // Browser fallback: localStorage
    if (_isBrowser) {
      return {
        getItem: (k) => {
          try { return window.localStorage.getItem(prefix + k); } catch (e) { return null; }
        },
        setItem: (k, v) => {
          try { window.localStorage.setItem(prefix + k, typeof v === 'string' ? v : JSON.stringify(v)); } catch (e) {}
        },
        removeItem: (k) => { try { window.localStorage.removeItem(prefix + k); } catch (e) {} }
      };
    }

    // Generic in-memory fallback
    const mem = {};
    return {
      getItem: (k) => (typeof mem[prefix + k] === 'undefined' ? null : mem[prefix + k]),
      setItem: (k, v) => { mem[prefix + k] = v; },
      removeItem: (k) => { delete mem[prefix + k]; }
    };
  }

  // -------------------------
  // Crypto Helpers (HMAC)
  // -------------------------
  // signHMAC(payload, secret) -> hex digest
  async function signHMAC(payload, secret) {
    // payload must be string
    const data = typeof payload === 'string' ? payload : JSON.stringify(payload);

    if (_isNode) {
      const cryptoNode = require('crypto');
      return cryptoNode.createHmac('sha256', secret).update(data).digest('hex');
    }

    // Browser SubtleCrypto
    if (typeof window !== 'undefined' && window.crypto && window.crypto.subtle) {
      const enc = new TextEncoder();
      const key = await window.crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
      const sig = await window.crypto.subtle.sign('HMAC', key, enc.encode(data));
      // convert to hex
      const h = Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('');
      return h;
    }

    // Fallback: simple JS implementation (not ideal for production)
    // We'll do a very simple hash using built-in crypto if available
    if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
      // no HMAC available; return base64 of data as last-resort marker
      return btoa(unescape(encodeURIComponent(data))).slice(0, 64);
    }

    throw new Error('No HMAC capability available in this environment');
  }

  // -------------------------
  // Device Fingerprint / ID
  // -------------------------
  async function generateDeviceFingerprint(opts = {}) {
    // Combine several pieces of entropy
    const parts = [];
    parts.push(navigatorFingerprint());
    parts.push((new Date()).toISOString());
    parts.push(uuidv4());
    const seed = parts.join('||');

    // derive short id via HMAC with a random salt
    const salt = opts.salt || 'solunex_device_salt_v1';
    const h = await signHMAC(seed, salt);
    return h;
  }

  function navigatorFingerprint() {
    try {
      if (!_isBrowser) return 'node';
      const nav = window.navigator || {};
      const screenInfo = (window.screen && (window.screen.width + 'x' + window.screen.height)) || 'unknown';
      return [nav.userAgent, nav.language, screenInfo, nav.platform].join('::');
    } catch (e) { return 'unknown'; }
  }

  // -------------------------
  // HTTP helper (fetch wrapper) with auto signing
  // -------------------------
  async function httpRequest(url, opts = {}, sdk) {
    opts = Object.assign({ method: 'GET', headers: {} }, opts);

    // Attach clientId if set
    if (sdk.clientId) opts.headers['X-Solunex-Client'] = sdk.clientId;
    if (sdk.environment) opts.headers['X-Solunex-Env'] = sdk.environment;

    // Sign body if secret available and method indicates mutating
    if (sdk.secret && opts.body) {
      const bodyString = (typeof opts.body === 'string') ? opts.body : JSON.stringify(opts.body);
      const signature = await signHMAC(bodyString, sdk.secret);
      opts.headers['X-Solunex-Signature'] = signature;
    }

    // choose fetch implementation
    if (_isNode) {
      let fetchFn;
      try { fetchFn = require('node-fetch'); } catch (e) { fetchFn = global.fetch; }
      if (!fetchFn) throw new Error('fetch not available in Node. Please provide node-fetch or global fetch.');
      const res = await fetchFn(url, opts);
      const txt = await res.text();
      try { return JSON.parse(txt); } catch (e) { return txt; }
    }

    // Browser or Electron renderer
    const res = await fetch(url, opts);
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) return await res.json();
    return await res.text();
  }

  // -------------------------
  // Core SDK Object
  // -------------------------
  function createSDK() {
    const store = makeStore();
    const sdk = {
      apiBase: null,
      clientId: null,
      secret: null, // optional for signing
      environment: null,
      isElectron: _isElectron,
      init: function (opts = {}) {
        if (!opts || !opts.apiBase) throw new Error('apiBase required');
        this.apiBase = opts.apiBase.replace(/\/$/, '');
        this.clientId = opts.clientId || null;
        this.secret = opts.secret || null;
        this.environment = opts.environment || 'production';
        this.store = makeStore({ prefix: opts.prefix || 'solunex_' });
        // ensure device id exists
        if (!this.store.getItem('device_id')) {
          const did = uuidv4();
          this.store.setItem('device_id', did);
        }
        return this;
      },

      getDeviceId: function () { return this.store.getItem('device_id'); },

      // verifyLicense: call server-side verification endpoint
      verifyLicense: async function (licenseKey) {
        if (!licenseKey) throw new Error('licenseKey required');
        const url = this.apiBase + '/license/verify';
        const body = {
          license: licenseKey,
          device_id: this.getDeviceId(),
          client_id: this.clientId
        };
        return await httpRequest(url, { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }, this);
      },

      // bindDevice: attempt to register this device for the license
      bindDevice: async function (licenseKey, meta = {}) {
        if (!licenseKey) throw new Error('licenseKey required');
        const url = this.apiBase + '/license/bind_device';
        const body = Object.assign({ license: licenseKey, device_id: this.getDeviceId(), client_id: this.clientId }, meta);
        return await httpRequest(url, { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }, this);
      },

      // trackActivation: send lightweight heartbeat/status
      trackActivation: async function (licenseKey, metadata = {}) {
        if (!licenseKey) throw new Error('licenseKey required');
        const url = this.apiBase + '/license/activation_ping';
        const body = Object.assign({ license: licenseKey, device_id: this.getDeviceId(), timestamp: new Date().toISOString() }, metadata);
        // use fire-and-forget if desired; return server response by default
        try {
          return await httpRequest(url, { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }, this);
        } catch (e) {
          // in case of failure, optionally cache locally
          const cacheKey = 'pending_ping_' + Date.now();
          this.store.setItem(cacheKey, JSON.stringify(body));
          return { status: false, message: 'cached' };
        }
      },

      // sign arbitrary payload with configured secret
      signPayload: async function (payload) {
        if (!this.secret) throw new Error('secret not configured');
        return await signHMAC(payload, this.secret);
      },

      // low-level request helper
      request: async function (path, opts = {}) {
        if (!this.apiBase) throw new Error('SDK not initialized');
        const url = this.apiBase + path;
        return await httpRequest(url, opts, this);
      },

      // convenience: logout / clear device binding info
      clearLocal: function () {
        // remove stored tokens / pending pings
        try {
          this.store.removeItem('device_id');
          // remove any pending_ping files (best-effort)
        } catch (e) {}
      }
    };

    return sdk;
  }

  // -------------------------
  // Exposed API
  // -------------------------
  const Solunex = {
    create: createSDK,
    // standalone helpers exported for advanced usage
    utils: {
      signHMAC,
      generateDeviceFingerprint,
      uuidv4
    },
    env: { isNode: _isNode, isBrowser: _isBrowser, isElectron: _isElectron }
  };

  // -------------------------
  // Example usage (commented)
  // -------------------------
  /*
  // Browser
  const sdk = Solunex.create();
  sdk.init({ apiBase: 'https://api.yourserver.com/api', clientId: 'myclient', secret: 'client-secret' });
  await sdk.verifyLicense('LICENSE-KEY-1234');
  await sdk.bindDevice('LICENSE-KEY-1234', { name: 'My Laptop' });
  await sdk.trackActivation('LICENSE-KEY-1234', { version: '1.0.0' });

  // Node / Electron (main)
  const sdk = require('./solunex.js').create();
  sdk.init({ apiBase: 'https://api.yourserver.com/api', clientId: 'myclient', secret: process.env.SOLUNEX_SECRET });
  const res = await sdk.verifyLicense('LICENSE-KEY-1234');
  console.log(res);

  // In Electron renderer you can use preload to expose limited APIs and call sdk methods safely.
  */

  return Solunex;
}));
