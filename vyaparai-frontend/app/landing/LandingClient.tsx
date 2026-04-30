'use client';

import { useEffect, useRef, useState, type CSSProperties } from 'react';

export default function LandingClient() {
  const navRef = useRef<HTMLElement | null>(null);
  const stepsLineRef = useRef<HTMLDivElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* Navbar scrolled state */
    const onScroll = () => {
      const nav = navRef.current;
      if (!nav) return;
      if (window.scrollY > 12) nav.classList.add('scrolled');
      else nav.classList.remove('scrolled');
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    /* Reveal on scroll + count-up + steps line */
    const animateCounters = (container: Element) => {
      container.querySelectorAll<HTMLElement>('[data-count]').forEach((el) => {
        if (el.dataset._done) return;
        el.dataset._done = '1';
        const target = parseFloat(el.dataset.count || '0');
        const suffix = el.dataset.suffix || '';
        const dur = reduced ? 0 : 1500;
        const start = performance.now();
        const ease = (t: number) => 1 - Math.pow(1 - t, 3);
        const tick = (now: number) => {
          const t = Math.min(1, (now - start) / dur);
          const v = target * ease(t);
          el.textContent =
            (target >= 100
              ? Math.round(v).toLocaleString('en-IN')
              : v.toFixed(target % 1 ? 1 : 0)) + suffix;
          if (t < 1) requestAnimationFrame(tick);
          else
            el.textContent =
              (target >= 100 ? Math.round(target).toLocaleString('en-IN') : target) + suffix;
        };
        if (reduced) el.textContent = target + suffix;
        else requestAnimationFrame(tick);
      });
    };

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('in');
            animateCounters(entry.target);
            if ((entry.target as HTMLElement).id === 'steps') {
              stepsLineRef.current?.classList.add('active');
            }
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0, rootMargin: '0px 0px -8% 0px' }
    );

    root.querySelectorAll('.reveal, .reveal-children, #steps').forEach((el) => io.observe(el));

    /* Force-reveal anything already in view on first paint */
    const rafId = requestAnimationFrame(() => {
      root.querySelectorAll<HTMLElement>('.reveal, .reveal-children').forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) {
          el.classList.add('in');
          animateCounters(el);
        }
      });
    });

    /* Tilt-toward-cursor on cards */
    const cardCleanups: Array<() => void> = [];
    if (!reduced && window.matchMedia('(hover: hover)').matches) {
      const cards = root.querySelectorAll<HTMLElement>(
        '.module-card, .price, .who-card, .notif, .shot, .prob-card'
      );
      cards.forEach((card) => {
        const onMove = (e: MouseEvent) => {
          const r = card.getBoundingClientRect();
          const x = (e.clientX - r.left) / r.width - 0.5;
          const y = (e.clientY - r.top) / r.height - 0.5;
          card.style.transform = `translateY(-4px) rotateX(${(-y * 4).toFixed(
            2
          )}deg) rotateY(${(x * 4).toFixed(2)}deg)`;
        };
        const onLeave = () => {
          card.style.transform = '';
        };
        card.addEventListener('mousemove', onMove);
        card.addEventListener('mouseleave', onLeave);
        cardCleanups.push(() => {
          card.removeEventListener('mousemove', onMove);
          card.removeEventListener('mouseleave', onLeave);
        });
      });
    }

    /* Hero parallax */
    let parallaxScroll: ((this: Window, ev: Event) => void) | null = null;
    if (!reduced) {
      const laptop = root.querySelector<HTMLElement>('.hero-laptop');
      const phone = root.querySelector<HTMLElement>('.hero .hero-phone');
      parallaxScroll = () => {
        const y = Math.min(window.scrollY, 600);
        if (laptop) laptop.style.transform = `rotate(-2deg) translateY(${y * 0.06}px)`;
        if (phone) phone.style.translate = `0 ${y * 0.02}px`;
      };
      window.addEventListener('scroll', parallaxScroll, { passive: true });
    }

    return () => {
      window.removeEventListener('scroll', onScroll);
      if (parallaxScroll) window.removeEventListener('scroll', parallaxScroll);
      cancelAnimationFrame(rafId);
      io.disconnect();
      cardCleanups.forEach((fn) => fn());
    };
  }, []);

  const closeDrawer = () => setDrawerOpen(false);

  return (
    <div className="refloat-root" ref={rootRef}>
      {/* NAV */}
      <nav className="nav" id="nav" aria-label="Primary" ref={navRef}>
        <div className="wrap nav-inner">
          <a href="#" className="logo" aria-label="Refloat home">
            <span className="logo-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <path
                  d="M3 14c2 1.5 4 1.5 6 0s4-1.5 6 0 4 1.5 6 0"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M3 18c2 1.5 4 1.5 6 0s4-1.5 6 0 4 1.5 6 0"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity=".55"
                />
                <path
                  d="M12 3v6M9 6l3-3 3 3"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            Refloat
          </a>
          <div className="nav-links" role="menubar">
            <a href="#features" role="menuitem">Features</a>
            <a href="#modules" role="menuitem">Modules</a>
            <a href="#how" role="menuitem">How It Works</a>
            <a href="#pricing" role="menuitem">Pricing</a>
            <a href="#about" role="menuitem">About</a>
          </div>
          <div className="nav-cta">
            <a href="#" className="btn btn-ghost btn-sm">Login</a>
            <a href="#pricing" className="btn btn-primary btn-sm">Start Free Trial</a>
            <button
              className="menu-btn"
              id="menuBtn"
              aria-label="Open menu"
              aria-expanded={drawerOpen}
              onClick={() => setDrawerOpen((v) => !v)}
            >
              <span></span>
            </button>
          </div>
        </div>
      </nav>

      <div
        className={`drawer${drawerOpen ? ' open' : ''}`}
        id="drawer"
        aria-hidden={!drawerOpen}
        onClick={(e) => {
          const t = e.target as HTMLElement;
          if (t.classList.contains('drawer') || t.tagName === 'A') closeDrawer();
        }}
      >
        <div className="drawer-panel" role="dialog" aria-label="Mobile menu">
          <a href="#features">Features</a>
          <a href="#modules">Modules</a>
          <a href="#how">How It Works</a>
          <a href="#pricing">Pricing</a>
          <a href="#about">About</a>
          <a href="#" className="btn btn-ghost">Login</a>
          <a href="#pricing" className="btn btn-primary">Start Free Trial</a>
        </div>
      </div>

      {/* HERO */}
      <header className="hero">
        <div className="hero-bg" aria-hidden="true">
          <div className="mesh m1"></div>
          <div className="mesh m2"></div>
          <div className="mesh m3"></div>
          <div className="hero-shape s1" style={{ ['--r' as any]: '15deg' } as CSSProperties}></div>
          <div className="hero-shape s2"></div>
          <div className="hero-shape s3" style={{ ['--r' as any]: '-12deg' } as CSSProperties}></div>
        </div>
        <div className="wrap hero-grid">
          <div className="hero-copy reveal">
            <span className="guarantee">
              <span className="seal" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12l4 4L19 6" />
                </svg>
              </span>
              <span><span className="pct">15–20%</span> growth guaranteed</span>
              <span className="sep"></span>
              <span style={{ color: 'var(--c-body)', fontWeight: 500 }}>in 3 months — or your money back</span>
            </span>
            <h1>
              Your business has a pulse. <span className="accent">Refloat</span> helps you read it.
            </h1>
            <p className="lead">
              The first AI growth assistant built for Indian MSMEs. Health monitoring, marketing automation, export discovery, and government schemes — all in one beautifully designed mobile app and web dashboard.
            </p>
            <div className="hero-cta">
              <a href="#pricing" className="btn btn-primary">Start 14-Day Free Trial</a>
              <a href="#" className="btn btn-ghost">
                <svg viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.7" />
                  <path d="M10 8.5v7l6-3.5-6-3.5z" fill="currentColor" />
                </svg>
                Watch 2-min Demo
              </a>
            </div>
            <div className="hero-stores">
              <a href="#" className="store" aria-label="Download on iOS">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M16.4 12.7c0-2.5 2-3.7 2.1-3.8-1.2-1.7-3-2-3.7-2-1.6-.2-3 .9-3.8.9-.8 0-2-.9-3.3-.9-1.7 0-3.3 1-4.1 2.5-1.8 3.1-.5 7.7 1.3 10.2.9 1.2 1.9 2.6 3.3 2.5 1.3 0 1.8-.8 3.4-.8 1.6 0 2 .8 3.4.8 1.4 0 2.3-1.2 3.1-2.4.9-1.4 1.3-2.7 1.4-2.8-.1 0-2.7-1-2.7-4.2zM13.7 5.2c.7-.8 1.2-2 1-3.2-1.1.1-2.4.7-3.1 1.6-.7.7-1.3 2-1.1 3.1 1.2.1 2.5-.6 3.2-1.5z" />
                </svg>
                <span className="label">
                  <span className="small">Download on the</span>
                  <span className="big">iOS App Store</span>
                </span>
              </a>
              <a href="#" className="store" aria-label="Get it on Android">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M3.6 20.6l9.4-9.4-9.4-9.4c-.3.2-.6.6-.6 1.1v16.6c0 .5.3.9.6 1.1zm10.5-8.3l3-3L5.6 1.4l8.5 10.9zM5.6 22.6l11.5-7.9-3-3L5.6 22.6zm14.7-9.5l-2.7-1.6-2.9 2.9 2.9 2.9 2.7-1.6c.7-.4.7-2.2 0-2.6z" />
                </svg>
                <span className="label">
                  <span className="small">Get it on</span>
                  <span className="big">Google Play</span>
                </span>
              </a>
              <a href="#" className="store web" aria-label="Open Web Dashboard">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                  <rect x="3" y="4" width="18" height="13" rx="2" />
                  <path d="M8 21h8M10 17v4M14 17v4" />
                </svg>
                <span className="label">
                  <span className="small">Or use it on</span>
                  <span className="big">Web Dashboard</span>
                </span>
              </a>
            </div>
            <div className="trust">
              <span>Trusted by retailers, manufacturers &amp; exporters across India</span>
              <div className="trust-logos">
                <span className="trust-logo"><span className="dot"></span>Surat Textiles Co.</span>
                <span className="trust-logo"><span className="dot"></span>Kochi Spice House</span>
                <span className="trust-logo"><span className="dot"></span>Ludhiana Works</span>
              </div>
            </div>
          </div>

          {/* DEVICE STACK */}
          <div className="hero-device-wrap reveal">
            <div className="hero-laptop" aria-hidden="true">
              <div className="laptop-screen">
                <div className="laptop-side">
                  <div className="ls-logo"><span className="m"></span>Refloat</div>
                  <div className="ls-item active"><span className="b"></span>Dashboard</div>
                  <div className="ls-item"><span className="b"></span>Marketing</div>
                  <div className="ls-item"><span className="b"></span>Schemes</div>
                  <div className="ls-item"><span className="b"></span>Exports</div>
                  <div className="ls-item"><span className="b"></span>Reports</div>
                </div>
                <div className="laptop-main">
                  <div className="lm-row">
                    <div className="lm-card"><div className="lab">Revenue · 30d</div><div className="val">₹4.82L</div><div className="delta">▲ 12.4%</div></div>
                    <div className="lm-card"><div className="lab">Health Score</div><div className="val">67</div><div className="delta dn">▼ 5</div></div>
                    <div className="lm-card"><div className="lab">ROAS</div><div className="val">3.2×</div><div className="delta">▲ 0.4</div></div>
                  </div>
                  <div className="lm-chart">
                    <div className="lab">Health trend · 90d</div>
                    <svg viewBox="0 0 200 60" preserveAspectRatio="none">
                      <defs>
                        <linearGradient id="lg1" x1="0" x2="0" y1="0" y2="1">
                          <stop offset="0" stopColor="#13C4A3" stopOpacity=".4" />
                          <stop offset="1" stopColor="#13C4A3" stopOpacity="0" />
                        </linearGradient>
                      </defs>
                      <path d="M0,42 L20,38 L40,40 L60,30 L80,32 L100,22 L120,28 L140,20 L160,24 L180,14 L200,18 L200,60 L0,60 Z" fill="url(#lg1)" />
                      <path d="M0,42 L20,38 L40,40 L60,30 L80,32 L100,22 L120,28 L140,20 L160,24 L180,14 L200,18" stroke="#13C4A3" strokeWidth="1.5" fill="none" />
                    </svg>
                  </div>
                </div>
              </div>
            </div>

            <div className="hero-phone" role="img" aria-label="Refloat mobile app dashboard">
              <div className="phone-notch"></div>
              <div className="phone-screen">
                <div className="phone-status">
                  <span>9:41</span>
                  <span className="icons"><span></span><span></span><span className="bat"></span></span>
                </div>
                <div className="phone-body">
                  <div className="ph-greet">
                    <div>
                      <h4>Namaste, Anjali</h4>
                      <div className="ph-sub">Café Bloom · MG Road</div>
                    </div>
                    <div className="av">A</div>
                  </div>

                  <div className="score-card">
                    <div className="score-row">
                      <div>
                        <div className="score-lab">Business Health</div>
                        <div className="score-num"><span data-count="67">0</span></div>
                        <div className="score-tag">▲ +4 this week</div>
                      </div>
                      <svg viewBox="0 0 60 60" width="60" height="60" style={{ position: 'relative', zIndex: 1 }}>
                        <circle cx="30" cy="30" r="24" stroke="rgba(255,255,255,0.18)" strokeWidth="6" fill="none" />
                        <circle cx="30" cy="30" r="24" stroke="#13C4A3" strokeWidth="6" fill="none" strokeLinecap="round" strokeDasharray="150.8" strokeDashoffset="49.7" transform="rotate(-90 30 30)" />
                      </svg>
                    </div>
                    <svg className="score-spark" viewBox="0 0 200 36" preserveAspectRatio="none">
                      <path d="M0,28 L20,26 L40,22 L60,24 L80,18 L100,20 L120,14 L140,16 L160,10 L180,12 L200,6" stroke="#7defc9" strokeWidth="2" fill="none" strokeLinecap="round" />
                    </svg>
                  </div>

                  <div className="alert-card">
                    <div className="ico" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 2l9 16H3L12 2z" />
                        <line x1="12" y1="9" x2="12" y2="13" />
                        <circle cx="12" cy="16" r="0.8" fill="currentColor" />
                      </svg>
                    </div>
                    <div className="txt">
                      <p className="ttl">New competitor 450m away</p>
                      <p className="des">Café Bloom opened on MG Road. Revenue may dip 6–9% in 2 weeks.</p>
                    </div>
                  </div>

                  <div className="quick-row">
                    <div className="qa"><span className="qi"></span>Reviews</div>
                    <div className="qa"><span className="qi"></span>Ads</div>
                    <div className="qa"><span className="qi"></span>Schemes</div>
                    <div className="qa"><span className="qi"></span>Reports</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* GUARANTEE STRIP */}
      <section className="guarantee-strip" style={{ padding: '22px 0' }}>
        <div className="wrap">
          <div className="row">
            <div className="seal" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2l2.4 2.6 3.5-.5.5 3.5L21 10l-2.6 2.4.5 3.5-3.5.5L12 19l-2.4-2.6-3.5.5-.5-3.5L3 10l2.6-2.4-.5-3.5 3.5-.5L12 2z" />
                <path d="M9 12l2 2 4-4" />
              </svg>
            </div>
            <div style={{ textAlign: 'left' }}>
              <h3><span className="pct">15–20%</span> growth guaranteed in 3 months — or your money back.</h3>
              <p className="sub">Verified across 1,200+ Indian MSMEs. Measured against your own baseline, not vanity metrics.</p>
            </div>
            <span className="divider"></span>
            <a href="#pricing" className="btn btn-amber btn-sm" style={{ height: '42px' }}>Claim the Guarantee</a>
          </div>
        </div>
      </section>

      {/* PROBLEM */}
      <section id="problem">
        <div className="wrap">
          <div className="section-head reveal">
            <span className="eyebrow amber">The Problem</span>
            <h2>Running a business in India shouldn&apos;t feel like flying blind.</h2>
            <p>Most Indian MSME owners discover problems only when their bank balance drops. We think that&apos;s far too late.</p>
          </div>
          <div className="problem-grid reveal-children">
            <div className="prob-card">
              <div className="prob-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18" />
                </svg>
              </div>
              <div className="prob-stat"><span data-count="63" data-suffix="M+">0</span></div>
              <p>MSMEs in India have zero structured access to business intelligence — only spreadsheets, gut feel, and word of mouth.</p>
            </div>
            <div className="prob-card">
              <div className="prob-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 17l6-6 4 4 8-8" />
                  <path d="M14 7h7v7" />
                </svg>
              </div>
              <div className="prob-stat"><span data-count="72" data-suffix="%">0</span></div>
              <p>Of small business owners discover problems only after their bank balance drops or a key customer churns.</p>
            </div>
            <div className="prob-card">
              <div className="prob-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="4" y="3" width="16" height="18" rx="2" />
                  <path d="M8 7h8M8 11h8M8 15h5" />
                </svg>
              </div>
              <div className="prob-stat">₹<span data-count="14">0</span>K Cr</div>
              <p>In government schemes go unclaimed every year because the docs are dense, English-heavy, and never reach the right business.</p>
            </div>
          </div>
        </div>
      </section>

      {/* MODULES */}
      <section id="features">
        <div className="wrap">
          <div className="section-head reveal">
            <span className="eyebrow">Five intelligent modules</span>
            <h2 id="modules">One unified platform. Five intelligent modules.</h2>
            <p>The Fitbit + CFO + Export Consultant + Marketing Agency for every Indian MSME — for as little as ₹999/month.</p>
          </div>

          <div className="modules">
            <article className="module-card feature reveal">
              <span className="mod-tag">Module 01 · Featured</span>
              <div className="mod-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 12h3l2-6 4 12 2-6h7" />
                </svg>
              </div>
              <h3>Business Health Monitor</h3>
              <p className="pitch">Real-time scoring of revenue, reviews, competitors, and employee signals — like a pulse oximeter for your business.</p>
              <ul className="mod-list">
                <li>0–100 score with momentum arrows and 7/30/90/365-day trends</li>
                <li>Live category benchmarks against businesses like yours</li>
                <li>Push notifications the moment something breaks</li>
              </ul>
              <div className="feat-preview">
                <div className="feat-gauge"><span>67</span></div>
                <div className="info">
                  <div className="t">Live · café bloom</div>
                  <div className="d"><span className="arr">▲</span>+4 this week · revenue ₹4.82L</div>
                </div>
              </div>
            </article>

            <article className="module-card reveal">
              <span className="mod-tag">Module 02</span>
              <div className="mod-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 11l18-7-7 18-3-7-8-4z" />
                </svg>
              </div>
              <h3>AI Marketing Agent</h3>
              <p className="pitch">Autonomous Google + Meta campaigns and a weekly content calendar in your business&apos;s voice.</p>
              <ul className="mod-list">
                <li>Copy generated, A/B tested, and scaled automatically</li>
                <li>Instagram, Facebook &amp; LinkedIn calendar — pre-scheduled</li>
                <li>Approve every ad and post with a single tap</li>
              </ul>
            </article>

            <article className="module-card reveal">
              <span className="mod-tag">Module 03</span>
              <div className="mod-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18" />
                </svg>
              </div>
              <h3>Export Opportunity Engine</h3>
              <p className="pitch">Maps your products to HS codes and the top 3 international markets that actually want them.</p>
              <ul className="mod-list">
                <li>Export-readiness checklist: RCMC, certifications, freight</li>
                <li>Real Indian exporters already winning in those markets</li>
                <li>Compliance progress tracking, end-to-end</li>
              </ul>
            </article>

            <article className="module-card reveal">
              <span className="mod-tag">Module 04</span>
              <div className="mod-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 7h16M4 12h16M4 17h10" />
                  <circle cx="18" cy="17" r="2.4" />
                </svg>
              </div>
              <h3>Government Schemes Finder</h3>
              <p className="pitch">Matches your business to CGTMSE, MUDRA, PMEGP, PLI, PM Vishwakarma, GeM and more.</p>
              <ul className="mod-list">
                <li>Step-by-step in-app application guides — Hindi or English</li>
                <li>Eligibility confidence scores so you don&apos;t chase dead ends</li>
                <li>Deadline reminders 30 days in advance</li>
              </ul>
            </article>

            <article className="module-card wide reveal">
              <span className="mod-tag">Module 05</span>
              <div className="mod-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="4" width="18" height="16" rx="2" />
                  <path d="M7 16V11M12 16V8M17 16v-3" />
                </svg>
              </div>
              <h3>Unified Analytics Dashboard</h3>
              <p className="pitch">Single view of sales, ads, exports, and scheme status — perfectly synced across mobile and web.</p>
              <ul className="mod-list">
                <li>Custom report builder, exportable as PDF or CSV</li>
                <li>Multi-location view for distributors and chains</li>
                <li>CA firm dashboards available on Enterprise</li>
              </ul>
            </article>
          </div>
        </div>
      </section>

      {/* SHOWCASE */}
      <section className="showcase">
        <div className="wrap">
          <div className="showcase-hero">
            <div className="reveal">
              <span className="eyebrow">Product Showcase</span>
              <h2>Designed for the way Indian business owners actually work.</h2>
              <p>Refloat shows you the three things that matter every morning: how healthy your business is, what to act on next, and which money is on the table you haven&apos;t picked up yet.</p>
              <p className="showcase-cap" style={{ textAlign: 'left', margin: '20px 0 0' }}>
                Available on iOS, Android, and any modern browser. Your data stays in sync everywhere.
              </p>
            </div>
            <div className="ph-wrap reveal">
              <div className="hero-phone">
                <div className="phone-notch"></div>
                <div className="phone-screen">
                  <div className="phone-status">
                    <span>9:41</span>
                    <span className="icons"><span></span><span></span><span className="bat"></span></span>
                  </div>
                  <div className="phone-body">
                    <div className="ph-greet">
                      <div>
                        <h4>Good morning, Anjali</h4>
                        <div className="ph-sub">Tuesday · 14 May</div>
                      </div>
                      <div className="av">A</div>
                    </div>
                    <div className="score-card">
                      <div className="score-row">
                        <div>
                          <div className="score-lab">Health Score</div>
                          <div className="score-num">67</div>
                          <div className="score-tag">▲ +4 this week</div>
                        </div>
                      </div>
                      <svg className="score-spark" viewBox="0 0 200 36" preserveAspectRatio="none">
                        <path d="M0,28 L20,24 L40,22 L60,26 L80,18 L100,20 L120,14 L140,16 L160,10 L180,12 L200,6" stroke="#7defc9" strokeWidth="2" fill="none" strokeLinecap="round" />
                      </svg>
                    </div>
                    <div className="alert-card">
                      <div className="ico">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12l4 4L19 6" /></svg>
                      </div>
                      <div className="txt">
                        <p className="ttl">3 actions ready for today</p>
                        <p className="des">Reply to 2 reviews · approve weekly Instagram post</p>
                      </div>
                    </div>
                    <div className="alert-card">
                      <div className="ico" style={{ background: 'rgba(19,196,163,0.12)', color: '#0fa78b' }}>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v20M2 12h20" /></svg>
                      </div>
                      <div className="txt">
                        <p className="ttl">CGTMSE — you may qualify</p>
                        <p className="des">Collateral-free loans up to ₹5 crore. 92% confidence.</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="showcase-grid reveal-children">
            <div className="shot">
              <div className="lab">Live Health Score</div>
              <h4>Your business pulse, all day</h4>
              <div className="shot-mock gauge-mock">
                <div className="gauge"><span className="num">67</span></div>
                <div className="arrow">▲ +4 this week</div>
              </div>
            </div>
            <div className="shot">
              <div className="lab">Marketing Campaigns</div>
              <h4>Active ads &amp; ROAS</h4>
              <div className="shot-mock ad-mock">
                <div className="ad-row"><span className="ad-pill">G</span><span className="nm">Search · Café visits</span><span className="roas">3.2×</span></div>
                <div className="ad-row"><span className="ad-pill meta">M</span><span className="nm">Reels · Weekend</span><span className="roas">4.1×</span></div>
                <div className="ad-chart">
                  <svg viewBox="0 0 200 60" preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="lg2" x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0" stopColor="#13C4A3" stopOpacity=".35" />
                        <stop offset="1" stopColor="#13C4A3" stopOpacity="0" />
                      </linearGradient>
                    </defs>
                    <path d="M0,46 L25,40 L50,34 L75,30 L100,24 L125,28 L150,18 L175,22 L200,12 L200,60 L0,60 Z" fill="url(#lg2)" />
                    <path d="M0,46 L25,40 L50,34 L75,30 L100,24 L125,28 L150,18 L175,22 L200,12" stroke="#13C4A3" strokeWidth="1.6" fill="none" />
                  </svg>
                </div>
              </div>
            </div>
            <div className="shot">
              <div className="lab">Schemes Matched For You</div>
              <h4>Money you can actually claim</h4>
              <div className="shot-mock scheme-mock">
                <div className="scheme-row">
                  <span className="ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-6 9 6v11H3z" /></svg></span>
                  <span className="nm">CGTMSE — ₹5 Cr loan</span>
                  <span className="conf">92%</span>
                </div>
                <div className="scheme-row">
                  <span className="ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M9 12l2 2 4-4" /></svg></span>
                  <span className="nm">MUDRA Tarun</span>
                  <span className="conf">87%</span>
                </div>
                <div className="scheme-row">
                  <span className="ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7l8-4 8 4-8 4-8-4z" /><path d="M4 12l8 4 8-4M4 17l8 4 8-4" /></svg></span>
                  <span className="nm">PMEGP Subsidy</span>
                  <span className="conf med">71%</span>
                </div>
              </div>
            </div>
          </div>

          <p className="showcase-cap">
            Available on iOS, Android, and any modern browser. Your data stays in sync — everywhere.
          </p>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how" style={{ background: '#fff' }}>
        <div className="wrap">
          <div className="section-head reveal">
            <span className="eyebrow">How It Works</span>
            <h2>From signup to first insight in under 10 minutes.</h2>
            <p>No sales calls. No onboarding consultant. Read-only access — you stay in control of every connection.</p>
          </div>
          <div className="steps reveal-children" id="steps">
            <div className="steps-line" id="stepsLine" aria-hidden="true" ref={stepsLineRef}>
              <svg viewBox="0 0 1000 4" preserveAspectRatio="none">
                <path d="M0,2 C250,2 250,2 500,2 C750,2 750,2 1000,2" />
              </svg>
            </div>
            <div className="step"><div className="step-num">01</div><h4>Sign up with your GST number</h4><p>We auto-fill your business profile from the GST portal. No forms, no typing.</p></div>
            <div className="step"><div className="step-num">02</div><h4>Connect your accounts</h4><p>Google Reviews, your POS, and ad accounts — read-only, one tap each.</p></div>
            <div className="step"><div className="step-num">03</div><h4>Refloat starts monitoring</h4><p>Within 24 hours we begin tracking your metrics, competitors, and reviews.</p></div>
            <div className="step"><div className="step-num">04</div><h4>See your first health report</h4><p>Open the app or web dashboard for your first health score and action items.</p></div>
          </div>
        </div>
      </section>

      {/* WHO IT'S FOR */}
      <section>
        <div className="wrap">
          <div className="section-head reveal">
            <span className="eyebrow amber">Who It&apos;s For</span>
            <h2>Built for the businesses that build Bharat.</h2>
          </div>
          <div className="who-grid reveal-children">
            <div className="who-card">
              <div className="who-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 21V8l9-5 9 5v13" />
                  <path d="M9 21v-7h6v7" />
                </svg>
              </div>
              <h4>Small Manufacturers</h4>
              <p>Production planning and demand forecasting in one screen.</p>
            </div>
            <div className="who-card">
              <div className="who-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 8h16l-1 12H5L4 8z" />
                  <path d="M9 8V5a3 3 0 016 0v3" />
                </svg>
              </div>
              <h4>Retail Shop Owners</h4>
              <p>Sales tracking, reviews and competitor monitoring in real time.</p>
            </div>
            <div className="who-card">
              <div className="who-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 7h13v10H3z" />
                  <path d="M16 10h4l1 3v4h-5" />
                  <circle cx="7" cy="19" r="2" />
                  <circle cx="18" cy="19" r="2" />
                </svg>
              </div>
              <h4>Mid-Scale Distributors</h4>
              <p>Multi-channel performance and route-level visibility.</p>
            </div>
            <div className="who-card">
              <div className="who-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="4" y="4" width="16" height="16" rx="2" />
                  <path d="M4 9h16M9 4v16" />
                </svg>
              </div>
              <h4>D2C Product Sellers</h4>
              <p>Ad automation and weekly social content in your brand voice.</p>
            </div>
            <div className="who-card">
              <div className="who-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M2 12h20M12 2a14 14 0 010 20M12 2a14 14 0 000 20" />
                </svg>
              </div>
              <h4>Emerging Exporters</h4>
              <p>Market discovery, HS code mapping and compliance guidance.</p>
            </div>
          </div>
        </div>
      </section>

      {/* IN-APP NOTIFS */}
      <section className="notif-section">
        <div className="wrap">
          <div className="section-head reveal">
            <span className="eyebrow">In-App Experience</span>
            <h2>See exactly what you&apos;ll get.</h2>
            <p>Real notifications from real Refloat users — bilingual, actionable, never noise.</p>
          </div>
          <div className="notif-grid reveal-children">
            <article className="notif weekly">
              <div className="notif-head">
                <div className="notif-app">R</div>
                <div className="notif-meta"><div className="nm">Refloat</div><div className="tm">Mon · 9:00 AM</div></div>
              </div>
              <h4>Weekly Digest</h4>
              <p>Health Score <strong>67 ↓</strong> from 72. Revenue down 9%. New competitor detected: Café Bloom at MG Road (450m). Top action: reply to 2 negative reviews about wait times.</p>
              <div className="row-tags"><span className="tag">Score · 67</span><span className="tag">Revenue · ₹4.82L</span></div>
              <span className="pill">Weekly Digest</span>
            </article>
            <article className="notif alert">
              <div className="notif-head">
                <div className="notif-app" style={{ background: 'linear-gradient(135deg,#EF4444,#F4B860)' }}>!</div>
                <div className="notif-meta"><div className="nm">Refloat · Alert</div><div className="tm">Today · 2:14 PM</div></div>
              </div>
              <h4>Score dropped to 58</h4>
              <p>Score dropped to <strong>58</strong> (was 67). Main reason: 4 negative reviews this week mention <em>&ldquo;cold food delivery.&rdquo;</em> Quick action: check delivery packaging.</p>
              <div className="row-tags"><span className="tag">−9 in 7 days</span><span className="tag">Reviews · 4</span></div>
              <span className="pill">Score Drop</span>
            </article>
            <article className="notif scheme">
              <div className="notif-head">
                <div className="notif-app" style={{ background: 'linear-gradient(135deg,#10B981,#13C4A3)' }}>₹</div>
                <div className="notif-meta"><div className="nm">Refloat · Schemes</div><div className="tm">Yesterday · 6:32 PM</div></div>
              </div>
              <h4>You may be eligible: CGTMSE</h4>
              <p>Collateral-free loans up to <strong>₹5 crore</strong>. Based on your Udyam registration and revenue range, you likely qualify. Apply guide ready in Hindi.</p>
              <div className="row-tags"><span className="tag">92% match</span><span className="tag">Apply in 12 mins</span></div>
              <span className="pill">Scheme Match</span>
            </article>
          </div>
        </div>
      </section>

      {/* ABOUT */}
      <section id="about" style={{ background: '#fff' }}>
        <div className="wrap">
          <div className="about-grid">
            <div className="reveal">
              <span className="eyebrow">Why Refloat exists</span>
              <h2>India has the world&apos;s second-largest MSME ecosystem — and the smallest amount of intelligence reaching it.</h2>
              <p>A textile exporter in Surat, a spice retailer in Kochi, a small manufacturer in Ludhiana — they all run blind. They know their numbers a month after they happen. They learn about competitors when customers stop coming. They hear about government schemes when the deadline is over.</p>
              <p>Refloat was built to change that. We combine continuous passive monitoring with AI advice that&apos;s actually useful — in Hindi and English — delivered through a beautifully designed mobile app and a synced web dashboard.</p>
              <p>We replace the consultant you can&apos;t afford, the export agent you&apos;ve never met, and the marketing agency that doesn&apos;t return your calls. One platform. ₹999 a month.</p>
            </div>
            <div className="stats reveal-children">
              <div className="stat"><div className="v"><span data-count="63">0</span><span className="u">M+</span></div><p className="l">MSMEs in India — the second-largest ecosystem on earth.</p></div>
              <div className="stat"><div className="v"><span data-count="29">0</span><span className="u">%</span></div><p className="l">Of India&apos;s GDP contributed by MSMEs every year.</p></div>
              <div className="stat"><div className="v amber">$<span data-count="2">0</span><span className="u">T</span></div><p className="l">Export target for India by 2030 — and it needs you.</p></div>
              <div className="stat"><div className="v">₹<span data-count="999">0</span></div><p className="l">Starting price · vs ₹60K+ for human equivalents.</p></div>
            </div>
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section id="pricing" className="pricing">
        <div className="wrap">
          <div className="section-head reveal">
            <span className="eyebrow">Pricing</span>
            <h2>Replace ₹60K of consultants for ₹999.</h2>
            <p>14 days free. No credit card. Cancel anytime. Every plan includes Hindi + English support.</p>
          </div>
          <div className="price-grid reveal-children">
            <div className="price">
              <h3>Free Trial</h3>
              <p className="for">14 days · no credit card</p>
              <div className="num-line"><span className="price-num">₹0</span><span className="price-per">/14 days</span></div>
              <ul>
                <li>Full Pro access for 14 days</li>
                <li>Health Monitor + alerts</li>
                <li>Sample marketing campaign</li>
                <li>Cancel anytime</li>
              </ul>
              <a href="#" className="btn btn-ghost">Start Trial</a>
            </div>
            <div className="price">
              <h3>Growth</h3>
              <p className="for">Best for retailers &amp; small manufacturers</p>
              <div className="num-line"><span className="price-num">₹999</span><span className="price-per">/month</span></div>
              <ul>
                <li>Health Monitor &amp; in-app alerts</li>
                <li>Weekly social content calendar</li>
                <li>Government schemes finder</li>
                <li>Hindi + English support</li>
              </ul>
              <a href="#" className="btn btn-ghost">Choose Growth</a>
            </div>
            <div className="price popular">
              <span className="price-tag">Most Popular</span>
              <h3>Pro</h3>
              <p className="for">Best for D2C sellers &amp; active advertisers</p>
              <div className="num-line"><span className="price-num">₹1,999</span><span className="price-per">/month</span></div>
              <ul>
                <li>Everything in Growth</li>
                <li>Google &amp; Meta ad automation</li>
                <li>Export Opportunity Engine</li>
                <li>HS code mapping &amp; compliance</li>
                <li>Priority support</li>
              </ul>
              <a href="#" className="btn btn-amber">Choose Pro</a>
            </div>
            <div className="price">
              <h3>Enterprise</h3>
              <p className="for">Best for distributors &amp; mid-cap manufacturers</p>
              <div className="num-line"><span className="price-num">₹4,999</span><span className="price-per">/month</span></div>
              <ul>
                <li>Everything in Pro</li>
                <li>Multi-location dashboard</li>
                <li>CA firm dashboard access</li>
                <li>Custom report builder</li>
                <li>Dedicated success manager</li>
              </ul>
              <a href="#" className="btn btn-ghost">Talk to Sales</a>
            </div>
          </div>
        </div>
      </section>

      {/* PLATFORMS */}
      <section className="platforms">
        <div className="wrap">
          <div className="section-head reveal">
            <span className="eyebrow">Platforms</span>
            <h2>One account. Every device.</h2>
            <p>Real-time sync across all your devices. Built natively for mobile, optimized for desktop.</p>
          </div>
          <div className="plat-grid reveal-children">
            <div className="plat">
              <div className="plat-ico">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M16.4 12.7c0-2.5 2-3.7 2.1-3.8-1.2-1.7-3-2-3.7-2-1.6-.2-3 .9-3.8.9-.8 0-2-.9-3.3-.9-1.7 0-3.3 1-4.1 2.5-1.8 3.1-.5 7.7 1.3 10.2.9 1.2 1.9 2.6 3.3 2.5 1.3 0 1.8-.8 3.4-.8 1.6 0 2 .8 3.4.8 1.4 0 2.3-1.2 3.1-2.4.9-1.4 1.3-2.7 1.4-2.8-.1 0-2.7-1-2.7-4.2zM13.7 5.2c.7-.8 1.2-2 1-3.2-1.1.1-2.4.7-3.1 1.6-.7.7-1.3 2-1.1 3.1 1.2.1 2.5-.6 3.2-1.5z" />
                </svg>
              </div>
              <div><h4>iOS App</h4><p>Native build · iPhone &amp; iPad · iOS 15+</p></div>
            </div>
            <div className="plat">
              <div className="plat-ico">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M3.6 20.6l9.4-9.4-9.4-9.4c-.3.2-.6.6-.6 1.1v16.6c0 .5.3.9.6 1.1zm10.5-8.3l3-3L5.6 1.4l8.5 10.9zM5.6 22.6l11.5-7.9-3-3L5.6 22.6zm14.7-9.5l-2.7-1.6-2.9 2.9 2.9 2.9 2.7-1.6c.7-.4.7-2.2 0-2.6z" />
                </svg>
              </div>
              <div><h4>Android App</h4><p>On Google Play · Android 9+</p></div>
            </div>
            <div className="plat">
              <div className="plat-ico">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="4" width="18" height="13" rx="2" />
                  <path d="M8 21h8M10 17v4M14 17v4" />
                </svg>
              </div>
              <div><h4>Web Dashboard</h4><p>Open in any modern browser · no install</p></div>
            </div>
          </div>
        </div>
      </section>

      {/* TRUST */}
      <section className="trust-strip">
        <div className="wrap">
          <div className="row reveal-children">
            <div className="trust-item">
              <div className="ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l9 4v6c0 5-4 9-9 10-5-1-9-5-9-10V6l9-4z" /></svg></div>
              <div className="t">Indian data residency<br /><span style={{ fontWeight: 500, color: 'var(--c-muted)' }}>AWS Mumbai</span></div>
            </div>
            <div className="trust-item">
              <div className="ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l4 4L19 6" /></svg></div>
              <div className="t">DPDPA 2023 compliant<br /><span style={{ fontWeight: 500, color: 'var(--c-muted)' }}>Audited annually</span></div>
            </div>
            <div className="trust-item">
              <div className="ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2" /><path d="M7 11V7a5 5 0 0110 0v4" /></svg></div>
              <div className="t">Read-only API access<br /><span style={{ fontWeight: 500, color: 'var(--c-muted)' }}>We never write to your accounts</span></div>
            </div>
            <div className="trust-item">
              <div className="ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14H6L5 6m5 0V4a2 2 0 012-2h0a2 2 0 012 2v2" /></svg></div>
              <div className="t">One-tap data deletion<br /><span style={{ fontWeight: 500, color: 'var(--c-muted)' }}>Within 30 days, end-to-end</span></div>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq">
        <div className="wrap">
          <div className="section-head reveal">
            <span className="eyebrow">FAQ</span>
            <h2>Everything you&apos;d ask before signing up.</h2>
          </div>
          <div className="faq-list reveal-children">
            {[
              {
                q: 'Do I need to be tech-savvy to use Refloat?',
                a: 'No. The app is designed for first-time smartphone users. The whole experience works fully in Hindi or English, with voice-friendly menus and big tap targets. Most owners get to their first health report in under 10 minutes.',
              },
              {
                q: 'What POS systems do you integrate with?',
                a: "Petpooja, DotPe, and most major Indian POS providers including Posist, Posify, GoFrugal, and Marg ERP. If you don't see yours, our team adds new integrations every month — just request it.",
              },
              {
                q: 'Is my business data safe?',
                a: "Yes. We use read-only API access, host all data in AWS Mumbai (Indian data residency), and you can delete every byte we hold with one tap. We're DPDPA 2023 compliant and never sell or share your data.",
              },
              {
                q: 'Can I cancel anytime?',
                a: "Yes. No lock-in contracts. Cancel inside the app and you'll keep access until the end of your billing period. We refund unused time in the first 30 days, no questions asked.",
              },
              {
                q: 'Do you offer support in Hindi?',
                a: 'Yes. The entire app, every alert, and all AI advice is bilingual — Hindi and English, with regional rollouts for Tamil, Telugu, Marathi and Bengali coming through 2026. Our support team replies in your language of choice.',
              },
              {
                q: 'How long until I see results?',
                a: "Most owners get their first actionable insight within 7 days — usually a missed review, a competitor signal, or a scheme they didn't know they qualified for. Marketing automation results land in 2–4 weeks.",
              },
            ].map((item, i) => (
              <details className="faq" key={i}>
                <summary>
                  {item.q}
                  <span className="chev">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </span>
                </summary>
                <p className="ans">{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* FINAL CTA */}
      <section style={{ padding: 0 }}>
        <div className="final-cta reveal">
          <div className="final-cta-wrap">
            <h2>Stop guessing. Start growing.</h2>
            <p>14 days free. No credit card. Cancel anytime.</p>
            <div className="row">
              <a href="#" className="btn btn-amber">Download the App</a>
              <a href="#" className="btn btn-ghost">Open Web Dashboard</a>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer>
        <div className="wrap">
          <div className="foot-grid">
            <div className="foot-brand">
              <a href="#" className="logo">
                <span className="logo-mark">
                  <svg viewBox="0 0 24 24" fill="none">
                    <path d="M3 14c2 1.5 4 1.5 6 0s4-1.5 6 0 4 1.5 6 0" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M3 18c2 1.5 4 1.5 6 0s4-1.5 6 0 4 1.5 6 0" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity=".55" />
                    <path d="M12 3v6M9 6l3-3 3 3" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
                Refloat
              </a>
              <p>The Fitbit + CFO + Export Consultant + Marketing Agency for every Indian MSME.</p>
            </div>
            <div className="foot-col">
              <h5>Product</h5>
              <ul>
                <li><a href="#features">Features</a></li>
                <li><a href="#pricing">Pricing</a></li>
                <li><a href="#modules">Modules</a></li>
                <li><a href="#">Demo</a></li>
              </ul>
            </div>
            <div className="foot-col">
              <h5>Company</h5>
              <ul>
                <li><a href="#about">About</a></li>
                <li><a href="#">Blog</a></li>
                <li><a href="#">Careers</a></li>
                <li><a href="#">Press</a></li>
              </ul>
            </div>
            <div className="foot-col">
              <h5>Resources</h5>
              <ul>
                <li><a href="#">Help Center</a></li>
                <li><a href="#">API Docs</a></li>
                <li><a href="#">Status</a></li>
                <li><a href="#">Changelog</a></li>
              </ul>
            </div>
            <div className="foot-col">
              <h5>Legal</h5>
              <ul>
                <li><a href="#">Privacy</a></li>
                <li><a href="#">Terms</a></li>
                <li><a href="#">DPDPA</a></li>
                <li><a href="#">Data Deletion</a></li>
              </ul>
            </div>
          </div>
          <div className="foot-bottom">
            <span>Made in India for Bharat 🇮🇳 · © 2026 Refloat Technologies Pvt. Ltd.</span>
            <div className="foot-social">
              <a href="#" aria-label="Twitter">
                <svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" /></svg>
              </a>
              <a href="#" aria-label="LinkedIn">
                <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 3a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h14zm-7 8.5h-2v8h2v-4.2c0-1.1.9-2 2-2s2 .9 2 2V19.5h2V14a3.5 3.5 0 00-6-2.45V11.5zm-5 8h2V11h-2v8.5zm1-9.7a1.2 1.2 0 100-2.4 1.2 1.2 0 000 2.4z" /></svg>
              </a>
              <a href="#" aria-label="Instagram">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <rect x="3" y="3" width="18" height="18" rx="5" />
                  <circle cx="12" cy="12" r="4" />
                  <circle cx="17.5" cy="6.5" r="0.8" fill="currentColor" />
                </svg>
              </a>
              <a href="#" aria-label="YouTube">
                <svg viewBox="0 0 24 24" fill="currentColor"><path d="M23 7.2a3 3 0 00-2.1-2.1C19 4.5 12 4.5 12 4.5s-7 0-8.9.6A3 3 0 001 7.2 31 31 0 00.5 12 31 31 0 001 16.8a3 3 0 002.1 2.1c1.9.6 8.9.6 8.9.6s7 0 8.9-.6a3 3 0 002.1-2.1A31 31 0 0023.5 12 31 31 0 0023 7.2zM10 15.5v-7l6 3.5-6 3.5z" /></svg>
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
