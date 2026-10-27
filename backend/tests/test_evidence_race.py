def test_concurrent_evidence_collection_for_same_video_does_not_duplicate(fake):
    import asyncio

    from app import db
    from app.models import Evidence, Video
    from app.trending import ensure_youtube_evidence

    fake.client.get("/api/trending")
    with db.SessionLocal() as s:
        s.query(Evidence).delete()
        s.commit()

    class SlowComments:
        async def top_comments(self, video_id):
            await asyncio.sleep(0.05)
            return [], "ok"

    async def run():
        with db.SessionLocal() as a, db.SessionLocal() as b:
            va = a.query(Video).filter_by(video_id="vid14").one()
            vb = b.query(Video).filter_by(video_id="vid14").one()
            await asyncio.gather(
                ensure_youtube_evidence(a, va, SlowComments()), ensure_youtube_evidence(b, vb, SlowComments())
            )

    asyncio.run(run())
    with db.SessionLocal() as s:
        assert s.query(Evidence).filter_by(video_id="vid14").count() == 1
