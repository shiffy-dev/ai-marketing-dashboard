const RANKING = [
  {
    name: "Velocity",
    formula: "Views ÷ hours since publish",
    note: "How fast it is moving right now.",
  },
  {
    name: "Outlier ratio",
    formula: "Views ÷ channel audience",
    note: "How far it outruns the creator’s own reach.",
  },
  {
    name: "Engagement",
    formula: "(Likes + comments) ÷ views",
    note: "How strongly viewers react.",
  },
];

function Column({ title, children }) {
  return (
    <div>
      <p className="mb-4 text-eyebrow uppercase text-white">{title}</p>
      <ul className="space-y-3 text-sm">{children}</ul>
    </div>
  );
}

export default function Footer({ onPlatform }) {
  const go = (p) => {
    onPlatform(p);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  return (
    <footer className="bg-navy text-slate">
      <section className="mx-auto grid max-w-page gap-10 px-5 py-16 md:px-gutter md:py-20 lg:grid-cols-2 lg:gap-16">
        <div>
          <p className="mb-5 flex items-center gap-3 text-eyebrow uppercase text-cyan">
            <span
              aria-hidden
              className="h-hairline w-rule rounded-full bg-cyan"
            />
            How the ranking works
          </p>
          <h2 className="text-band text-white">
            Score = half velocity, half outlier ratio — ranked as percentiles.
          </h2>
          <p className="mt-5 max-w-lede border-t border-white/10 pt-5 text-sm leading-relaxed">
            Every video is compared with the rest of today’s pool, so a small
            creator with a breakout Short ranks above a big channel coasting on
            its subscriber base.
          </p>
        </div>
        <ul>
          {RANKING.map((r) => (
            <li
              key={r.name}
              className="flex flex-col gap-3 border-t border-white/10 py-5 last:border-b sm:flex-row sm:items-start sm:justify-between sm:gap-6"
            >
              <div>
                <p className="text-lede font-semibold text-white">{r.name}</p>
                <p className="mt-1 text-xs">{r.note}</p>
              </div>
              <p className="self-start rounded-md bg-white/5 sm:shrink-0 px-3 py-1.5 text-xs font-semibold text-cyan">
                {r.formula}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <div
        aria-hidden
        className="h-px bg-gradient-to-r from-transparent via-cyan/40 to-transparent"
      />

      <div
        style={{
          background:
            "radial-gradient(1200px 400px at 100% 0%, rgba(87,202,251,0.06), transparent)",
        }}
      >
        <div className="mx-auto grid max-w-page gap-10 px-5 py-14 sm:grid-cols-2 md:px-gutter lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <p className="text-h3 font-extrabold tracking-tight text-white">
              ecomma<span className="text-cyan">.</span>
            </p>
            <p className="mt-5 max-w-xs text-sm leading-relaxed">
              Short-form trend intelligence for ecommerce marketing teams in the
              UAE: what’s winning, and the evidence for why.
            </p>
          </div>
          <Column title="Dashboard">
            <li>
              <button
                onClick={() => go("youtube")}
                className="hover:text-white"
              >
                YouTube Shorts
              </button>
            </li>
            <li>
              <button
                onClick={() => go("instagram")}
                className="hover:text-white"
              >
                Instagram Reels
              </button>
            </li>
          </Column>
          <Column title="Data sources">
            <li>YouTube Data API (official)</li>
            <li>Apify · Instagram Reels</li>
            <li>Claude · evidence-backed analysis</li>
          </Column>
          <Column title="Market">
            <li className="font-semibold text-cyan">United Arab Emirates</li>
            <li>Asia/Dubai (GST)</li>
            <li>English &amp; Arabic</li>
          </Column>
        </div>
        <div className="mx-auto flex max-w-page flex-col gap-2 border-t border-white/10 px-5 py-6 text-xs sm:flex-row sm:justify-between md:px-gutter">
          <p>© {new Date().getFullYear()} Ecomma · AI Marketing Dashboard</p>
          <p>Analyses cite transcripts, comments and thumbnails as evidence.</p>
        </div>
      </div>
    </footer>
  );
}
