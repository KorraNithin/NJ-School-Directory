
import { useEffect, useMemo, useState } from "react";
import {
  Search,
  MapPin,
  School,
  Users,
  Globe,
  Phone,
  Mail,
  RefreshCw,
  ArrowUpRight,
  GraduationCap,
  Building2,
  ShieldCheck,
  Sparkles,
  X,
  SlidersHorizontal,
} from "lucide-react";
import {
  getDistricts,
  getSchools,
  getAdministrators,
} from "./api";
import "./App.css";

function App() {
  const [districts, setDistricts] = useState([]);
  const [schools, setSchools] = useState([]);
  const [administrators, setAdministrators] = useState([]);
  const [activeTab, setActiveTab] = useState("districts");
  const [search, setSearch] = useState("");
  const [districtFilter, setDistrictFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [districtRes, schoolRes, adminRes] = await Promise.all([
        getDistricts(),
        getSchools(),
        getAdministrators(),
      ]);

      setDistricts(districtRes.data || []);
      setSchools(schoolRes.data || []);
      setAdministrators(adminRes.data || []);
    } catch (err) {
      setError(
        err.response?.data?.error ||
        err.message ||
        "Unable to load directory data."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
  let cancelled = false;

  async function fetchDirectory() {
    try {
      setError("");

      const [districtRes, schoolRes, adminRes] = await Promise.all([
        getDistricts(),
        getSchools(),
        getAdministrators(),
      ]);

      if (!cancelled) {
        setDistricts(districtRes.data || []);
        setSchools(schoolRes.data || []);
        setAdministrators(adminRes.data || []);
      }
    } catch (err) {
      if (!cancelled) {
        setError(
          err.response?.data?.error ||
          err.message ||
          "Unable to load directory data."
        );
      }
    } finally {
      if (!cancelled) {
        setLoading(false);
      }
    }
  }

  fetchDirectory();

  return () => {
    cancelled = true;
  };
}, []);

  const filteredDistricts = useMemo(() => {
    const term = search.toLowerCase().trim();

    return districts.filter((district) =>
      `${district.name} ${district.city || ""} ${district.state || ""} ${district.zip || ""}`
        .toLowerCase()
        .includes(term)
    );
  }, [districts, search]);

  const filteredSchools = useMemo(() => {
    const term = search.toLowerCase().trim();

    return schools.filter((school) => {
      const matchesSearch =
        `${school.name} ${school.city || ""} ${school.districts?.name || ""}`
          .toLowerCase()
          .includes(term);

      const matchesDistrict =
        districtFilter === "all" ||
        String(school.district_id) === districtFilter;

      return matchesSearch && matchesDistrict;
    });
  }, [schools, search, districtFilter]);

  const filteredAdministrators = useMemo(() => {
    const term = search.toLowerCase().trim();

    return administrators.filter((admin) => {
      const matchesSearch =
        `${admin.name} ${admin.title || ""} ${admin.districts?.name || ""} ${admin.schools?.name || ""}`
          .toLowerCase()
          .includes(term);

      const matchesDistrict =
        districtFilter === "all" ||
        String(admin.district_id) === districtFilter;

      return matchesSearch && matchesDistrict;
    });
  }, [administrators, search, districtFilter]);

  const currentRecords =
    activeTab === "districts"
      ? filteredDistricts
      : activeTab === "schools"
        ? filteredSchools
        : filteredAdministrators;

  const currentCount = currentRecords.length;

  function changeTab(tab) {
    setActiveTab(tab);
    setSearch("");
    setDistrictFilter("all");
  }

  function clearSearch() {
    setSearch("");
    setDistrictFilter("all");
  }

  const tabs = [
    { id: "districts", label: "Districts", icon: Building2, count: districts.length },
    { id: "schools", label: "Schools", icon: School, count: schools.length },
    { id: "administrators", label: "Administrators", icon: Users, count: administrators.length },
  ];

  return (
    <div className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <div className="star-field" aria-hidden="true" />

      <header className="topbar">
        <a className="brand" href="/" aria-label="NJ School Directory home">
          <div className="brand-mark">
            <GraduationCap size={25} strokeWidth={1.8} />
          </div>
          <div className="brand-copy">
            <span className="brand-name">NJ<span>Directory</span></span>
            <span className="brand-caption">NEW JERSEY EDUCATION NETWORK</span>
          </div>
        </a>

        <div className="topbar-right">
          <div className="live-indicator">
            <span className="live-dot" />
            Directory portal
          </div>
          <button
            className="refresh-button"
            onClick={loadData}
            disabled={loading}
            aria-label="Refresh directory"
          >
            <RefreshCw size={15} className={loading ? "spin" : ""} />
            <span>{loading ? "Loading" : "Refresh data"}</span>
          </button>
        </div>
      </header>

      <main className="main-content">
        <section className="hero-section">
          <div className="hero-copy">
            <div className="eyebrow">
              <Sparkles size={13} />
              <span>NEW JERSEY · EDUCATION DIRECTORY</span>
            </div>

            <h1>
              The people behind
              <br />
              <span>New Jersey education.</span>
            </h1>

            <p className="hero-description">
              One place to explore school districts, schools, and education
              administrators across New Jersey.
            </p>

            <div className="hero-trust">
              <ShieldCheck size={16} />
              <span>Centralized public education directory</span>
              <span className="trust-separator">•</span>
              <span>Easy access to official sources</span>
            </div>
          </div>

          <div className="hero-visual" aria-hidden="true">
            <div className="orbit orbit-outer" />
            <div className="orbit orbit-inner" />
            <div className="hero-glow">
              <GraduationCap size={72} strokeWidth={1.15} />
            </div>
            <div className="floating-chip chip-top">
              <Building2 size={15} />
              <span>Districts</span>
            </div>
            <div className="floating-chip chip-bottom">
              <Users size={15} />
              <span>People & contacts</span>
            </div>
          </div>
        </section>

        <section className="stats-grid" aria-label="Directory statistics">
          <div className="stat-card">
            <div className="stat-icon stat-blue"><Building2 size={20} /></div>
            <div className="stat-content">
              <span className="stat-label">School districts</span>
              <strong>{districts.length.toLocaleString()}</strong>
              <span className="stat-note">Across New Jersey</span>
            </div>
            <div className="stat-decoration">01</div>
          </div>

          <div className="stat-card">
            <div className="stat-icon stat-purple"><School size={20} /></div>
            <div className="stat-content">
              <span className="stat-label">Schools</span>
              <strong>{schools.length.toLocaleString()}</strong>
              <span className="stat-note">Education institutions</span>
            </div>
            <div className="stat-decoration">02</div>
          </div>

          <div className="stat-card">
            <div className="stat-icon stat-cyan"><Users size={20} /></div>
            <div className="stat-content">
              <span className="stat-label">Administrators</span>
              <strong>{administrators.length.toLocaleString()}+</strong>
              <span className="stat-note">Available contact records</span>
            </div>
            <div className="stat-decoration">03</div>
          </div>
        </section>

        <section className="directory-panel">
          <div className="panel-heading">
            <div>
              <div className="section-kicker">EXPLORE THE DIRECTORY</div>
              <h2>Find the information you need.</h2>
              <p>Search by name, location, organization, or administrator title.</p>
            </div>
            <div className="secure-label">
              <ShieldCheck size={15} />
              Public information
            </div>
          </div>

          <div className="directory-tabs" role="tablist" aria-label="Directory categories">
            {tabs.map(({ id, label, icon: Icon, count }) => (
              <button
                key={id}
                role="tab"
                aria-selected={activeTab === id}
                className={`directory-tab ${activeTab === id ? "active" : ""}`}
                onClick={() => changeTab(id)}
              >
                <Icon size={17} />
                <span>{label}</span>
                <span className="tab-count">{count.toLocaleString()}</span>
              </button>
            ))}
          </div>

          <div className="search-toolbar">
            <div className="search-input-wrap">
              <Search size={19} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={
                  activeTab === "districts"
                    ? "Search districts by name or location..."
                    : activeTab === "schools"
                      ? "Search schools by name or district..."
                      : "Search administrators by name, title, or district..."
                }
                aria-label={`Search ${activeTab}`}
              />
              {search && (
                <button className="clear-search" onClick={() => setSearch("")} aria-label="Clear search">
                  <X size={16} />
                </button>
              )}
            </div>

            {activeTab !== "districts" && (
              <div className="filter-wrap">
                <SlidersHorizontal size={16} />
                <select
                  value={districtFilter}
                  onChange={(e) => setDistrictFilter(e.target.value)}
                  aria-label="Filter by district"
                >
                  <option value="all">All districts</option>
                  {districts.map((district) => (
                    <option key={district.id} value={district.id}>
                      {district.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div className="results-toolbar">
            <div className="results-title">
              <span className="results-pulse" />
              <strong>
                {activeTab === "districts"
                  ? "School districts"
                  : activeTab === "schools"
                    ? "Schools"
                    : "Administrators"}
              </strong>
              <span className="results-subtitle">Search results</span>
            </div>
            <div className="results-count">
              <strong>{currentCount.toLocaleString()}</strong>
              <span> records found</span>
              {(search || districtFilter !== "all") && (
                <button onClick={clearSearch}>Clear filters</button>
              )}
            </div>
          </div>

          {loading ? (
            <div className="state-message">
              <div className="loader-ring" />
              <strong>Loading directory</strong>
              <span>Gathering the latest available records...</span>
            </div>
          ) : error ? (
            <div className="state-message error-state">
              <div className="state-icon"><RefreshCw size={22} /></div>
              <strong>We couldn't load the directory.</strong>
              <span>{error}</span>
              <button className="retry-button" onClick={loadData}>Try again</button>
            </div>
          ) : currentCount === 0 ? (
            <div className="state-message">
              <div className="state-icon"><Search size={22} /></div>
              <strong>No matching records</strong>
              <span>Try another search term or clear your filters.</span>
              <button className="retry-button" onClick={clearSearch}>Clear filters</button>
            </div>
          ) : (
            <div className="records-list">
              {activeTab === "districts" && filteredDistricts.map((district) => (
                <article className="record-card" key={district.id}>
                  <div className="record-symbol district-symbol"><MapPin size={20} /></div>
                  <div className="record-details">
                    <div className="record-title-row">
                      <h3>{district.name}</h3>
                      <span className="record-type">DISTRICT</span>
                    </div>
                    <p className="record-description">
                      {[district.city, district.state, district.zip].filter(Boolean).join(", ") || "Location not available"}
                    </p>
                    <div className="record-links">
                      {district.phone && (
                        <a href={`tel:${district.phone}`}><Phone size={14} />{district.phone}</a>
                      )}
                      {district.website && (
                        <a href={district.website} target="_blank" rel="noreferrer">
                          <Globe size={14} />Official website <ArrowUpRight size={12} />
                        </a>
                      )}
                    </div>
                  </div>
                  <div className="record-arrow"><ArrowUpRight size={17} /></div>
                </article>
              ))}

              {activeTab === "schools" && filteredSchools.map((school) => (
                <article className="record-card" key={school.id}>
                  <div className="record-symbol school-symbol"><School size={20} /></div>
                  <div className="record-details">
                    <div className="record-title-row">
                      <h3>{school.name}</h3>
                      <span className="record-type">SCHOOL</span>
                    </div>
                    <p className="record-description">
                      {school.districts?.name || "District not available"}
                    </p>
                    <p className="record-location">
                      <MapPin size={13} />
                      {[school.city, school.state, school.zip].filter(Boolean).join(", ") || "Location not available"}
                    </p>
                    <div className="record-links">
                      {school.phone && (
                        <a href={`tel:${school.phone}`}><Phone size={14} />{school.phone}</a>
                      )}
                      {school.website && (
                        <a href={school.website} target="_blank" rel="noreferrer">
                          <Globe size={14} />School website <ArrowUpRight size={12} />
                        </a>
                      )}
                    </div>
                  </div>
                  <div className="record-arrow"><ArrowUpRight size={17} /></div>
                </article>
              ))}

              {activeTab === "administrators" && filteredAdministrators.map((admin) => (
                <article className="record-card" key={admin.id}>
                  <div className="record-symbol admin-symbol"><Users size={20} /></div>
                  <div className="record-details">
                    <div className="record-title-row">
                      <h3>{admin.name}</h3>
                      <span className="record-type">ADMINISTRATOR</span>
                    </div>
                    <p className="admin-title">{admin.title || "Administrator"}</p>
                    <p className="record-description">
                      {admin.schools?.name || admin.districts?.name || "Organization not available"}
                    </p>
                    <div className="record-links">
                      {admin.email && (
                        <a href={`mailto:${admin.email}`}><Mail size={14} />{admin.email}</a>
                      )}
                      {admin.phone && (
                        <a href={`tel:${admin.phone}`}><Phone size={14} />{admin.phone}</a>
                      )}
                      {admin.source_url && (
                        <a href={admin.source_url} target="_blank" rel="noreferrer">
                          <Globe size={14} />Source <ArrowUpRight size={12} />
                        </a>
                      )}
                    </div>
                  </div>
                  <div className="record-arrow"><ArrowUpRight size={17} /></div>
                </article>
              ))}
            </div>
          )}

          {!loading && !error && currentCount > 0 && (
            <div className="list-footer">
              Showing <strong>{currentCount.toLocaleString()}</strong> matching records
              <span>·</span>
              Updated when you refresh the directory
            </div>
          )}
        </section>

        <footer className="site-footer">
          <div className="footer-brand">
            <div className="footer-mark"><GraduationCap size={18} /></div>
            <span>NJ<span>Directory</span></span>
          </div>
          <p>Making New Jersey education information easier to discover.</p>
          <div className="footer-note">
            Contact information is displayed when available. Please verify details with the linked official source.
          </div>
        </footer>
      </main>
    </div>
  );
}

export default App;
