import Link from "next/link";
import { Disclaimer } from "@/components/Disclaimer";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border">
        <div className="mx-auto max-w-6xl px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-primary">HireRight</span>
            <span className="text-sm font-medium text-muted-foreground">AI</span>
          </div>
          <Link
            href="/onboarding"
            className="inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Get Started Free
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-4 py-20 md:py-32 text-center">
        <h1 className="text-4xl md:text-6xl font-bold tracking-tight text-foreground leading-tight">
          Hiring Your First Employee?
          <br />
          <span className="text-primary">Don&apos;t Get Fined.</span>
        </h1>
        <p className="mt-6 text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto leading-relaxed">
          AI-powered compliance assistant that tells you exactly what you need to
          do to legally hire in your state. From EIN to employee handbook, we&apos;ve
          got you covered.
        </p>
        <div className="mt-10">
          <Link
            href="/onboarding"
            className="inline-flex items-center justify-center rounded-lg bg-primary px-8 py-4 text-lg font-semibold text-primary-foreground hover:bg-primary/90 transition-colors shadow-lg shadow-primary/20"
          >
            Get Started Free &rarr;
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-4 py-16">
        <div className="grid gap-8 md:grid-cols-3">
          <FeatureCard
            emoji="📋"
            title="State-Specific Compliance Checklist"
            description="Not a generic template. A step-by-step checklist customized for your state, industry, and business type. Check items off as you go."
          />
          <FeatureCard
            emoji="⚖️"
            title="W-2 or 1099?"
            description="Answer a few questions and find out if your worker should be classified as an employee or independent contractor. Avoid costly misclassification fines."
          />
          <FeatureCard
            emoji="📄"
            title="Employee Handbook Generator"
            description="Generate a state-compliant employee handbook in minutes. Covers wages, leave, anti-harassment policy, and more. Download as Word doc."
          />
        </div>
      </section>

      {/* Social Proof */}
      <section className="bg-secondary/50 py-16">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-2xl font-bold text-center mb-10">
            Real Problems, Real Business Owners
          </h2>
          <div className="grid gap-6 md:grid-cols-3">
            <QuoteCard
              quote="I just hired my first employee and had NO idea I needed to register with so many agencies. Almost missed the deadline for workers' comp."
              source="r/smallbusiness"
            />
            <QuoteCard
              quote="Got hit with a $12,000 fine because I classified my workers as 1099 when they should have been W-2. Wish I had known about the ABC test."
              source="Indie Hackers"
            />
            <QuoteCard
              quote="I spent 3 days trying to figure out what labor law posters I need to put up. Every state is different and the info is scattered everywhere."
              source="r/smallbusiness"
            />
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="mx-auto max-w-3xl px-4 py-16">
        <h2 className="text-2xl font-bold text-center mb-10">
          Frequently Asked Questions
        </h2>
        <div className="space-y-6">
          <FAQItem
            question="Is this legal advice?"
            answer="No. HireRight AI provides general information about employment compliance requirements. We strongly recommend consulting a licensed employment attorney for advice specific to your situation."
          />
          <FAQItem
            question="Which states do you support?"
            answer="We currently support California and Texas, with more states coming soon. Federal requirements are included for all users."
          />
          <FAQItem
            question="How much does it cost?"
            answer="HireRight AI is currently free during our early access period. We want to make sure it's genuinely helpful before we charge for it."
          />
          <FAQItem
            question="Is my business information stored?"
            answer="Your business details are stored only in your browser's local storage. We do not store your sensitive business information on any server."
          />
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-12">
        <div className="mx-auto max-w-6xl px-4 text-center">
          <div className="text-lg font-bold text-primary mb-4">HireRight AI</div>
          <Disclaimer variant="inline" />
        </div>
      </footer>
    </div>
  );
}

function FeatureCard({
  emoji,
  title,
  description,
}: {
  emoji: string;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-8 hover:shadow-md transition-shadow">
      <div className="text-4xl mb-4">{emoji}</div>
      <h3 className="text-xl font-semibold mb-2">{title}</h3>
      <p className="text-muted-foreground leading-relaxed">{description}</p>
    </div>
  );
}

function QuoteCard({ quote, source }: { quote: string; source: string }) {
  return (
    <div className="rounded-xl bg-card border border-border p-6">
      <p className="text-foreground italic leading-relaxed">&ldquo;{quote}&rdquo;</p>
      <p className="mt-4 text-sm text-muted-foreground">&mdash; {source}</p>
    </div>
  );
}

function FAQItem({ question, answer }: { question: string; answer: string }) {
  return (
    <div className="border-b border-border pb-6">
      <h3 className="text-lg font-semibold mb-2">{question}</h3>
      <p className="text-muted-foreground leading-relaxed">{answer}</p>
    </div>
  );
}
