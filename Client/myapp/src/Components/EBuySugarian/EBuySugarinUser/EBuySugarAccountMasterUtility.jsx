import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Button,
    Grid,
    Paper,
    Typography,
    Modal,
    Box
} from "@mui/material";
import Pagination from "../../../Common/UtilityCommon/Pagination";
import SearchBar from "../../../Common/UtilityCommon/SearchBar";
import PerPageSelect from "../../../Common/UtilityCommon/PerPageSelect";
import axios from "axios";

const API_URL = process.env.REACT_APP_API;

function EBuySugarAccountMasterUtility() {
    const [fetchedData, setFetchedData] = useState([]);
    const [filteredData, setFilteredData] = useState([]);
    const [perPage, setPerPage] = useState(15);
    const [searchTerm, setSearchTerm] = useState("");
    const [currentPage, setCurrentPage] = useState(1);
    const [gstNo, setGstNo] = useState("");
    const [openModal, setOpenModal] = useState(false);
    const [redirectPathYes, setRedirectPathYes] = useState("/path-yes");
    const [redirectPathNo, setRedirectPathNo] = useState("/path-no");

    const navigate = useNavigate();
    const location = useLocation();
    const { gst_no } = location.state || {};

    const fetchData = async () => {
        try {
            if (gstNo) {
                const apiUrl = `${API_URL}/getBy_GstNo?gst_no=${gstNo}`;
                const response = await axios.get(apiUrl);
                if (response.data && Array.isArray(response.data.accountMasterData)) {
                    if (response.data.accountMasterData.length === 0) {
                        handleOpenModal();
                    } else {
                        setFetchedData(response.data.accountMasterData);
                        setFilteredData(response.data.accountMasterData);
                    }
                }
            }
        } catch (error) {
            console.error("Error fetching data:", error);
        }
    };

    useEffect(() => {
        if (gst_no) {
            setGstNo(gst_no);
        }
    }, [gst_no]);

    useEffect(() => {
        fetchData();
    }, [gstNo]);

    useEffect(() => {
        const filtered = fetchedData.filter(post => {
            const searchTermLower = searchTerm.toLowerCase();
            return Object.keys(post).some(key =>
                String(post[key]).toLowerCase().includes(searchTermLower)
            );
        });
        setFilteredData(filtered);
        setCurrentPage(1);
    }, [searchTerm, fetchedData]);

    const handlePerPageChange = (event) => {
        setPerPage(Number(event.target.value));
        setCurrentPage(1);
    };

    const handleSearchTermChange = (event) => {
        setSearchTerm(event.target.value);
    };

    const handleMapClick = async (post) => {
        try {
            // Send POST request to insert-accountmaster
            const response = await axios.post(`${API_URL}/insert-accountmaster`, {
                master_data: post,
                contact_data: [], // Include contact_data if necessary
            });
    
            if (response.status === 201) {
                console.log('Data inserted successfully:', response.data);
    
                // Update the state to hide the mapped record
                setFetchedData(fetchedData.map(item => 
                    item.Ac_Code === post.Ac_Code ? { ...item, mapped: true } : item
                ));
                setFilteredData(filteredData.map(item => 
                    item.Ac_Code === post.Ac_Code ? { ...item, mapped: true } : item
                ));
    
                
            } else {
                console.error('Error inserting data:', response.data);
            }
            // Navigate to the new route
            navigate('/eBuySugarian-user-utility');
        } catch (error) {
            console.error('Error:', error);
        }
    };
    

    const pageCount = Math.ceil(filteredData.length / perPage);

    const paginatedPosts = filteredData.slice((currentPage - 1) * perPage, currentPage * perPage);

    const handlePageChange = (pageNumber) => {
        setCurrentPage(pageNumber);
    };

    const handleSearchClick = () => {
        // Handle search button click if needed
    };

    const handleBack = () => {
        navigate("/DashBoard");
    };

    const handleOpenModal = () => setOpenModal(true);
    const handleCloseModal = () => setOpenModal(false);

    const handleYesClick = () => {
        navigate("/account-master");
        handleCloseModal();
    };

    const handleNoClick = () => {
        navigate(redirectPathNo);
        handleCloseModal();
    };

    const modalStyle = {
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: 400,
        bgcolor: 'background.paper',
        border: '2px solid #000',
        boxShadow: 24,
        p: 4,
    };

    return (
        <div className="container" style={{ padding: '20px', overflow: 'hidden' }}>
            <Typography variant="h4" gutterBottom style={{ textAlign: 'center', marginBottom: '20px' }}>
                eBuySugar Account Master
            </Typography>
            <Grid container spacing={2} alignItems="center">
                <Grid item>
                    <Button variant="contained" color="secondary" onClick={handleBack}>
                        Back
                    </Button>
                </Grid>
                <Grid item>
                    <PerPageSelect value={perPage} onChange={handlePerPageChange} />
                </Grid>
                <Grid item xs={12} sm={4} sx={{ marginLeft: 2 }}>
                    <SearchBar
                        value={searchTerm}
                        onChange={handleSearchTermChange}
                        onSearchClick={handleSearchClick}
                    />
                </Grid>
                <Grid item xs={12}>
                    <Paper elevation={3}>
                        <TableContainer style={{ maxHeight: '400px' }}>
                            <Table stickyHeader>
                                <TableHead>
                                    <TableRow>
                                        <TableCell>A/c Code</TableCell>
                                        <TableCell>A/c Type</TableCell>
                                        <TableCell>A/c Name</TableCell>
                                        <TableCell>Short Name</TableCell>
                                        <TableCell>Commission</TableCell>
                                        <TableCell>Address</TableCell>
                                        <TableCell>State Code</TableCell>
                                        <TableCell>GST No</TableCell>
                                        <TableCell>PAN</TableCell>
                                        <TableCell>FSSAI</TableCell>
                                        <TableCell>Adhar No</TableCell>
                                        <TableCell>Mobile No</TableCell>
                                        <TableCell>A/c Id</TableCell>
                                        <TableCell>Action</TableCell> {/* New Column for Action */}
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {paginatedPosts.filter(post => !post.mapped).map((post) => (
                                        <TableRow
                                            key={post.Ac_Code}
                                            className="row-item"
                                            style={{ cursor: "pointer" }}
                                        >
                                            <TableCell>{post.Ac_Code}</TableCell>
                                            <TableCell>{post.Ac_type}</TableCell>
                                            <TableCell>{post.Ac_Name_E}</TableCell>
                                            <TableCell>{post.Short_Name}</TableCell>
                                            <TableCell>{post.Ac_rate}</TableCell>
                                            <TableCell>{post.Address_E}</TableCell>
                                            <TableCell>{post.GSTStateCode}</TableCell>
                                            <TableCell>{post.Gst_No}</TableCell>
                                            <TableCell>{post.PanLink}</TableCell>
                                            <TableCell>{post.FSSAI}</TableCell>
                                            <TableCell>{post.adhar_no}</TableCell>
                                            <TableCell>{post.Mobile_No}</TableCell>
                                            <TableCell>{post.accoid}</TableCell>
                                            <TableCell>
                                                <Button onClick={() => handleMapClick(post)}>Map</Button>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    </Paper>
                </Grid>
                <Grid item xs={12}>
                    <Pagination
                        pageCount={pageCount}
                        currentPage={currentPage}
                        onPageChange={handlePageChange}
                    />
                </Grid>
            </Grid>

            {/* Modal */}
            <Modal
                open={openModal}
                onClose={handleCloseModal}
                aria-labelledby="modal-title"
                aria-describedby="modal-description"
            >
                <Box sx={modalStyle}>
                    <Typography id="modal-title" variant="h6" component="h2">
                        No Account Found
                    </Typography>
                    <Typography id="modal-description" sx={{ mt: 2 }}>
                        No Account Found... Please Add Account
                    </Typography>
                    <Grid container spacing={2} style={{ marginTop: 20 }}>
                        <Grid item>
                            <Button variant="contained" color="primary" onClick={handleYesClick}>
                                Yes
                            </Button>
                        </Grid>
                        <Grid item>
                            <Button variant="outlined" color="secondary" onClick={handleNoClick}>
                                No
                            </Button>
                        </Grid>
                    </Grid>
                </Box>
            </Modal>
        </div>
    );
}

export default EBuySugarAccountMasterUtility;
