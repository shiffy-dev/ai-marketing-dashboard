import { useCallback, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { aggregateKey, refreshPlatform, trendingKey } from "./api.js";
import AggregateStrip from "./components/AggregateStrip.jsx";
import AnalysisDrawer from "./components/AnalysisDrawer.jsx";
import Footer from "./components/Footer.jsx";
import Header from "./components/Header.jsx";
import Hero from "./components/Hero.jsx";
import VideoCard, { VideoCardSkeleton } from "./components/VideoCard.jsx";
import { Notice, Section } from "./components/ui.jsx";

export default function App() {
  const [platform, setPlatform] = useState("youtube");
  const [relevant, setRelevant] = useState(true);
  const [selected, setSelected] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState(null);
  const { mutate: globalMutate } = useSWRConfig();

  const key = trendingKey(platform, relevant);
  const { data, error, isLoading, mutate } = useSWR(key);
  const items = data?.items || [];

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    setRefreshError(null);
    try {
      await mutate(await refreshPlatform(platform, relevant), {
        revalidate: false,
      });
      globalMutate(aggregateKey(platform, relevant));
    } catch (e) {
      setRefreshError(e.message);
    } finally {
      setRefreshing(false);
    }
  }, [mutate, globalMutate, platform, relevant]);

  const closeDrawer = useCallback(() => setSelected(null), []);
  const switchPlatform = useCallback((p) => {
    setPlatform(p);
    setSelected(null);
  }, []);

  return (
    <div className="min-h-screen">
      <Header platform={platform} onPlatform={switchPlatform} />
      <main>
        <Hero
          platform={platform}
          data={data}
          isLoading={isLoading}
          relevant={relevant}
          onRelevant={setRelevant}
          onRefresh={onRefresh}
          refreshing={refreshing}
        />

        <Section
          eyebrow={
            platform === "youtube"
              ? "Top 10 · ranked by velocity + outlier ratio"
              : data?.dataset?.sample
                ? "Sample data · placeholder reels"
                : "Trending among tracked UAE accounts"
          }
          title="The videos, and why they work."
        >
          {refreshError && (
            <div className="mb-6">
              <Notice tone="warning" title="Refresh failed">
                {refreshError}
              </Notice>
            </div>
          )}
          {error && (
            <Notice
              tone="error"
              title="Couldn't load trending videos"
              action={
                <button className="btn btn-secondary" onClick={() => mutate()}>
                  Try again
                </button>
              }
            >
              {error.message}
            </Notice>
          )}
          {!error && isLoading && (
            <div className="grid gap-5 lg:grid-cols-2">
              {Array.from({ length: 6 }, (_, i) => (
                <VideoCardSkeleton key={i} />
              ))}
            </div>
          )}
          {!error && !isLoading && items.length === 0 && (
            <Notice
              title={
                platform === "instagram"
                  ? "No Instagram data yet"
                  : "No trending videos yet"
              }
            >
              {platform === "instagram"
                ? "Instagram Reels come from a curated dataset that hasn’t been loaded yet."
                : "Nothing stored yet. Try refreshing from YouTube."}
            </Notice>
          )}
          {items.length > 0 && (
            <>
              <AggregateStrip platform={platform} relevant={relevant} />
              <div className="grid gap-5 md:gap-6 lg:grid-cols-2">
                {items.map((item) => (
                  <VideoCard
                    key={item.video_id}
                    item={item}
                    onOpen={setSelected}
                  />
                ))}
              </div>
            </>
          )}
        </Section>
      </main>
      <Footer onPlatform={switchPlatform} />
      {selected && <AnalysisDrawer item={selected} onClose={closeDrawer} />}
    </div>
  );
}
