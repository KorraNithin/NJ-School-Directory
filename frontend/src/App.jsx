
import { useEffect, useMemo, useState } from "react";
import {
  getDistricts,
  getSchools,
  getAdministrators,
} from "./api";
import {
  Search,
  MapPin,
  School,
  Users,
  Globe,
  Phone,
  Mail,
  RefreshCw,
} from "lucide-react";
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

      setDistricts(districtRes.data);
      setSchools(schoolRes.data);
      setAdministrators(adminRes.data);
    } catch (err) {
      setError(err.response?.data?.error || err.message || "Unable to load directory data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
  let cancelled = false;

  async function fetchData() {
    try {
      const [districtRes, schoolRes, adminRes] = await Promise.all([
        getDistricts(),
        getSchools(),
        getAdministrators(),
      ]);

      if (!cancelled) {
        setDistricts(districtRes.data);
        setSchools(schoolRes.data);
        setAdministrators(adminRes.data);
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

  fetchData();

  return () => {
    cancelled = true;
  };
}, []);

  const filteredDistricts = useMemo(() => {
    return districts.filter((district) =>
      `${district.name} ${district.city || ""} ${district.zip || ""}`
        .toLowerCase()
        .includes(search.toLowerCase())
    );
  }, [districts, search]);

  const filteredSchools = useMemo(() => {
    return schools.filter((school) => {
      const matchesSearch =
        `${school.name} ${school.city || ""} ${school.districts?.name || ""}`
          .toLowerCase()
          .includes(search.toLowerCase());

      const matchesDistrict =
        districtFilter === "all" ||
        String(school.district_id) === districtFilter;

      return matchesSearch && matchesDistrict;
    });
  }, [schools, search, districtFilter]);

  const filteredAdministrators = useMemo(() => {
    return administrators.filter((admin) => {
      const matchesSearch =
        `${admin.name} ${admin.title || ""} ${admin.districts?.name || ""} ${admin.schools?.name || ""}`
          .toLowerCase()
          .includes(search.toLowerCase());

      const matchesDistrict =
        districtFilter === "all" ||
        String(admin.district_id) === districtFilter;

      return matchesSearch && matchesDistrict;
    });
  }, [administrators, search, districtFilter]);

  const currentCount =
    activeTab === "districts"
      ? filteredDistricts.length
      : activeTab === "schools"
        ? filteredSchools.length
        : filteredAdministrators.length;

  function changeTab(tab) {
    setActiveTab(tab);
    setSearch("");
    setDistrictFilter("all");
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon"><School size={23} /></div>
          <div>
            <h1>NJ School Directory</h1>
            <p>New Jersey education contacts</p>
          </div>
        </div>
        <button className="refresh-button" onClick={loadData} disabled={loading}>
          <RefreshCw size={16} /> Refresh
        </button>
      </header>

      <main className="container">
        <section className="hero">
          <span className="eyebrow">NEW JERSEY • EDUCATION DIRECTORY</span>
          <h2>Find schools, districts and administrators.</h2>
          <p>Search education organizations and view their available contact information.</p>
        </section>

        <section className="stats">
          <div className="stat-card">
            <MapPin />
            <div><strong>{districts.length.toLocaleString()}</strong><span>Districts</span></div>
          </div>
          <div className="stat-card">
            <School />
            <div><strong>{schools.length.toLocaleString()}</strong><span>Schools</span></div>
          </div>
          <div className="stat-card">
            <Users />
            <div><strong>{administrators.length.toLocaleString()}</strong><span>Administrators</span></div>
          </div>
        </section>

        <section className="directory">
          <div className="tabs">
            <button className={activeTab === "districts" ? "active" : ""} onClick={() => changeTab("districts")}>Districts</button>
            <button className={activeTab === "schools" ? "active" : ""} onClick={() => changeTab("schools")}>Schools</button>
            <button className={activeTab === "administrators" ? "active" : ""} onClick={() => changeTab("administrators")}>Administrators</button>
          </div>

          <div className="filters">
            <div className="search-box">
              <Search size={19} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={`Search ${activeTab}...`}
              />
            </div>

            {activeTab !== "districts" && (
              <select value={districtFilter} onChange={(e) => setDistrictFilter(e.target.value)}>
                <option value="all">All districts</option>
                {districts.map((district) => (
                  <option key={district.id} value={district.id}>{district.name}</option>
                ))}
              </select>
            )}
          </div>

          <div className="results-heading">
            <strong>{activeTab.charAt(0).toUpperCase() + activeTab.slice(1)}</strong>
            <span>{currentCount.toLocaleString()} results</span>
          </div>

          {loading ? (
            <div className="message">Loading directory data...</div>
          ) : error ? (
            <div className="message error">
              {error}
              <button onClick={loadData}>Try again</button>
            </div>
          ) : currentCount === 0 ? (
            <div className="message">No matching records found.</div>
          ) : (
            <div className="records">
              {activeTab === "districts" && filteredDistricts.map((district) => (
                <article className="record" key={district.id}>
                  <div className="record-icon"><MapPin /></div>
                  <div className="record-main">
                    <h3>{district.name}</h3>
                    <p>{[district.city, district.state, district.zip].filter(Boolean).join(", ") || "Location not available"}</p>
                    <div className="contact-lines">
                      {district.phone && <span><Phone size={14} /> {district.phone}</span>}
                      {district.website && <a href={district.website} target="_blank" rel="noreferrer"><Globe size={14} /> Official website</a>}
                    </div>
                  </div>
                </article>
              ))}

              {activeTab === "schools" && filteredSchools.map((school) => (
                <article className="record" key={school.id}>
                  <div className="record-icon"><School /></div>
                  <div className="record-main">
                    <h3>{school.name}</h3>
                    <p>{school.districts?.name || "District not available"}</p>
                    <p>{[school.city, school.state, school.zip].filter(Boolean).join(", ")}</p>
                    <div className="contact-lines">
                      {school.phone && <span><Phone size={14} /> {school.phone}</span>}
                      {school.website && <a href={school.website} target="_blank" rel="noreferrer"><Globe size={14} /> School website</a>}
                    </div>
                  </div>
                </article>
              ))}

              {activeTab === "administrators" && filteredAdministrators.map((admin) => (
                <article className="record" key={admin.id}>
                  <div className="record-icon"><Users /></div>
                  <div className="record-main">
                    <h3>{admin.name}</h3>
                    <p>{admin.title || "Administrator"}</p>
                    <p>{admin.schools?.name || admin.districts?.name || "Organization not available"}</p>
                    <div className="contact-lines">
                      {admin.email && <a href={`mailto:${admin.email}`}><Mail size={14} /> {admin.email}</a>}
                      {admin.phone && <a href={`tel:${admin.phone}`}><Phone size={14} /> {admin.phone}</a>}
                      {admin.source_url && <a href={admin.source_url} target="_blank" rel="noreferrer"><Globe size={14} /> Source</a>}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <footer>
          Contact information is shown only when available in the collected records.
          Always verify details with the linked official source.
        </footer>
      </main>
    </div>
  );
}

export default App;
