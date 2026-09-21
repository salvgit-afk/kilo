"use client";

/**
 * Pagina principale: accesso, onboarding e sezioni.
 *
 * Il flusso ha tre stati: non autenticato (accesso/registrazione), account
 * senza profilo (onboarding), account con profilo (app). Il token vive in
 * `localStorage` e viene ripristinato all'avvio da `/auth/me`: se è scaduto
 * il backend risponde 401 e si torna alla schermata di accesso, senza
 * lasciare l'interfaccia bloccata su errori.
 *
 * Qui passano anche gli `Intent`: quando l'utente conferma un'azione
 * proposta dal coach, la pagina apre la sezione giusta e le consegna cosa
 * fare (una ricerca nel diario, una scheda da generare).
 */

import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { api, session, type AuthSession, type Profile } from "@/lib/api";
import type { Intent } from "@/lib/coach";
import { SECTION_ORDER, Shell, type SectionId } from "@/components/Shell";
import { Spinner } from "@/components/ui";
import { ChatBubble } from "@/components/ChatBubble";
import { ReminderBanner } from "@/components/ReminderBanner";
import { NotesProvider } from "@/lib/notes";
import { useSectionBadges } from "@/lib/badges";
import { Auth } from "@/components/sections/Auth";
import { Onboarding } from "@/components/sections/Onboarding";
import { Today } from "@/components/sections/Today";
import { Workout } from "@/components/sections/Workout";
import { Diary } from "@/components/sections/Diary";
import { Recipes } from "@/components/sections/Recipes";
import { Progress } from "@/components/sections/Progress";
import { Supplements } from "@/components/sections/Supplements";
import { ProfileSection } from "@/components/sections/ProfileSection";

export default function Page() {
  const [account, setAccount] = useState<AuthSession["user"] | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [section, setSection] = useState<SectionId>("oggi");
  const [loading, setLoading] = useState(true);
  const [intent, setIntent] = useState<Intent | null>(null);

  // Direzione dell'ultimo cambio di sezione: su mobile la nuova sezione
  // entra dal lato verso cui si sta "sfogliando".
  const [shown, setShown] = useState({ section, dir: 0 });
  if (shown.section !== section) {
    setShown({
      section,
      dir: Math.sign(SECTION_ORDER.indexOf(section) - SECTION_ORDER.indexOf(shown.section)),
    });
  }
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    const update = () => setMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const clearIntent = useCallback(() => setIntent(null), []);
  const runIntent = useCallback((next: Omit<Intent, "nonce">) => {
    setSection(next.section);
    setIntent({ ...next, nonce: Date.now() });
  }, []);

  useEffect(() => {
    if (!session.get()) {
      setLoading(false);
      return;
    }
    api
      .get<AuthSession>("/auth/me")
      .then((s) => {
        setAccount(s.user);
        setProfile(s.profile);
      })
      .catch(() => session.clear())
      .finally(() => setLoading(false));
  }, []);

  function onAuthenticated(s: AuthSession) {
    setAccount(s.user);
    setProfile(s.profile);
    setSection("oggi");
  }

  function logout() {
    session.clear();
    setAccount(null);
    setProfile(null);
  }

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner label="Carico…" />
      </div>
    );
  }

  if (!account) return <Auth onAuthenticated={onAuthenticated} />;
  if (!profile) return <Onboarding onCreated={setProfile} />;

  return (
    <NotesProvider profileId={profile.id} section={section}>
      <ShellWithBadges profileId={profile.id} active={section} onNavigate={setSection} profileName={profile.display_name}>
        <ReminderBanner profileId={profile.id} section={section} onNavigate={setSection} />
        {/* Solo animazione d'entrata. Con un'uscita in modalità "wait", la
            sezione Integratori (schede animate dell'esploratore) restava
            bloccata a opacità 0 e da lì ogni sezione appariva vuota. */}
        <motion.div
            key={section}
            initial={mobile ? { opacity: 0, x: shown.dir * 36 } : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, x: 0, y: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          >
            {section === "oggi" && <Today profile={profile} onNavigate={setSection} />}
            {section === "scheda" && (
              <Workout profile={profile} intent={intent} onIntentHandled={clearIntent} />
            )}
            {section === "diario" && (
              <Diary profileId={profile.id} intent={intent} onIntentHandled={clearIntent} />
            )}
            {section === "ricette" && (
              <Recipes profileId={profile.id} intent={intent} onIntentHandled={clearIntent} />
            )}
            {section === "progressi" && <Progress profileId={profile.id} />}
            {section === "integratori" && <Supplements profileId={profile.id} />}
            {section === "profilo" && (
              <ProfileSection
                profile={profile}
                email={account.email}
                isAdmin={account.is_admin}
                onUpdated={setProfile}
                onReset={logout}
              />
            )}
          </motion.div>
      </ShellWithBadges>

      <ChatBubble
        profileId={profile.id}
        section={section}
        onNavigate={setSection}
        onIntent={runIntent}
      />
    </NotesProvider>
  );
}


/** Il menu con i pallini di cosa c'è da segnare oggi. */
function ShellWithBadges({
  profileId,
  ...props
}: { profileId: number } & Omit<React.ComponentProps<typeof Shell>, "badges">) {
  const badges = useSectionBadges(profileId);
  return <Shell {...props} badges={badges} />;
}
