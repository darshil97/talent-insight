export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl items-center px-6 py-16">
      <div className="w-full rounded-2xl border border-slate-200 bg-white p-8 sm:p-12">
        <p className="text-sm font-semibold tracking-wide text-teal-800">
          TALENT INSIGHT
        </p>
        <h1 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">
          Evidence for better recruiting conversations.
        </h1>
        <p className="mt-5 max-w-xl text-base leading-7 text-slate-600">
          A recruiting assistant for reviewing candidate evidence, exploring job
          requirements, and preparing focused screening conversations. Recruiters
          make the final hiring decisions.
        </p>
        <p className="mt-8 border-t border-slate-200 pt-6 text-sm leading-6 text-slate-600">
          This application is in development. Job browsing, resume assessment and
          screening will become available in upcoming modules.
        </p>
      </div>
    </main>
  );
}
