export default function ConversationSummaryBar({ analyses }) {
  const allClaims = analyses.flatMap((item) => item.claims ?? []);
  const supported = allClaims.filter((claim) => claim.status === "supported").length;
  const uncertain = allClaims.filter((claim) => claim.status === "uncertain").length;
  const contested = allClaims.filter((claim) => claim.status === "contested").length;

  return (
    <section className="rounded-[30px] border border-white/10 bg-white/5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.24em] text-mute">Conversation summary</p>
          <h2 className="mt-2 font-display text-2xl text-text">Signal radar</h2>
        </div>
        <div className="flex flex-wrap gap-3 text-sm">
          <span className="rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-2 text-emerald-100">
            {supported} supported
          </span>
          <span className="rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-2 text-amber-100">
            {uncertain} uncertain
          </span>
          <span className="rounded-full border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-rose-100">
            {contested} contested
          </span>
        </div>
      </div>
    </section>
  );
}
