import { Navigate, Route, Routes } from "react-router-dom";
import AdminDashboard from "./features/admin/AdminDashboard";
import InterviewRoom from "./features/interview-room/InterviewRoom";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AdminDashboard />} />
      <Route path="/interview/:token" element={<InterviewRoom />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
