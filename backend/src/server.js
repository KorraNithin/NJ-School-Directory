
const express = require("express");
const cors = require("cors");
require("dotenv").config();

const supabase = require("./config/supabase");
const districtRoutes = require("./routes/districtRoutes");
const schoolRoutes = require("./routes/schoolRoutes");
const administratorRoutes = require("./routes/administratorRoutes");

const app = express();

app.use(cors());
app.use(express.json());
app.use("/api/districts", districtRoutes);
app.use("/api/schools", schoolRoutes);
app.use("/api/administrators", administratorRoutes);



app.get("/", (req, res) => {
  res.json({ message: "NJ School Directory API is running!" });
});

app.get("/api/health", async (req, res) => {
  try {
    const { data, error } = await supabase
      .from("districts")
      .select("id")
      .limit(1);

    if (error) throw error;

    res.json({
      status: "connected",
      message: "Supabase connection successful",
    });
  } catch (error) {
    res.status(500).json({
      status: "error",
      message: error.message,
    });
  }
});

const PORT = process.env.PORT || 5000;

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
