import { HashRouter, NavLink, Link, Route, Routes } from 'react-router-dom';
import { useClubs, useMeta } from './lib/data';
import { ClubDatalist, Status } from './components/ui';
import { dateLong } from './lib/format';
import Home from './pages/Home';
import Rise from './pages/Rise';
import AllTime from './pages/AllTime';
import Eras from './pages/Eras';
import ClubPage from './pages/Club';
import Matchups from './pages/Matchups';
import Rankings from './pages/Rankings';
import Greatest from './pages/Greatest';

const NAV: [string, string][] = [
  ['/rise', 'Rise & fall'], ['/alltime', 'All-time'], ['/eras', 'Eras'], ['/club', 'Club'],
  ['/matchups', 'Matchups'], ['/rankings', 'Rankings'], ['/greatest', 'Greatest'],
];

function Mark() {
  return (
    <svg className="brand-mark" viewBox="0 0 100 110" aria-hidden="true">
      <polygon points="50,3 95,28 95,82 50,107 5,82 5,28" fill="none" stroke="#3fd0ff" strokeWidth="5" />
      <polygon points="50,22 78,38 78,72 50,88 22,72 22,38" fill="rgba(63,208,255,.15)" stroke="#3fd0ff" strokeOpacity=".5" strokeWidth="2" />
      <circle cx="50" cy="55" r="9" fill="#3fd0ff" />
    </svg>
  );
}

export default function App() {
  const clubs = useClubs();
  const meta = useMeta();
  return (
    <HashRouter>
      <header className="top">
        <div className="top-inner">
          <Link to="/" className="brand"><Mark /><div><b>FOOTBALL ELO</b><span>EUROPE · 1955 → NOW</span></div></Link>
          <nav className="nav" aria-label="Sections">
            {NAV.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
          </nav>
          {meta.data && <div className="stamp">Data to {dateLong(meta.data.last_match_date)}</div>}
        </div>
      </header>
      <main className="shell">
        {clubs.data ? (
          <>
            <ClubDatalist clubs={clubs.data} />
            <Routes>
              <Route path="/" element={<Home clubs={clubs.data} />} />
              <Route path="/rise" element={<Rise clubs={clubs.data} />} />
              <Route path="/alltime" element={<AllTime clubs={clubs.data} />} />
              <Route path="/eras" element={<Eras clubs={clubs.data} />} />
              <Route path="/club" element={<ClubPage clubs={clubs.data} />} />
              <Route path="/club/:slug" element={<ClubPage clubs={clubs.data} />} />
              <Route path="/matchups" element={<Matchups clubs={clubs.data} />} />
              <Route path="/rankings" element={<Rankings clubs={clubs.data} />} />
              <Route path="/greatest" element={<Greatest clubs={clubs.data} />} />
              <Route path="*" element={<Home clubs={clubs.data} />} />
            </Routes>
          </>
        ) : <Status error={clubs.error} />}
        <p className="footer">
          Club Elo-style ratings from league, cup and European results since 1955. Crests and colours via ESPN and
          Transfermarkt; results from engsoccerdata, football-data.co.uk, RSSSF, Wikipedia, Transfermarkt and ESPN.
        </p>
      </main>
    </HashRouter>
  );
}
